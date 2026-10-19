import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import ErrorNote from '../components/ErrorNote'
import { errorMessage } from '../errors'
import ReviewView from '../components/ReviewView'
import { isFinished } from '../status'
import type { Review, Run } from '../types'

const POLL_MS = 2000

export default function RunPage() {
  const { id = '' } = useParams()
  const [run, setRun] = useState<Run | null>(null)
  const [review, setReview] = useState<Review | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    async function poll() {
      try {
        const next = await api.getRun(id)
        if (cancelled) return
        setRun(next)
        if (next.status === 'succeeded') {
          setReview(await api.getReview(id))
        }
        if (!isFinished(next.status)) timer = setTimeout(poll, POLL_MS)
      } catch (e) {
        if (!cancelled) setError(errorMessage(e))
      }
    }

    void poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [id])

  return (
    <div className="space-y-4">
      {run && (
        <Link to={`/projects/${run.project_id}`} className="text-sm text-blue-700 hover:underline">
          ← Project
        </Link>
      )}
      <ErrorNote message={error} />
      {!run && !error && <p>Loading…</p>}
      {run && !isFinished(run.status) && (
        <p role="status">
          Run {run.status}… (checking every {POLL_MS / 1000} s)
        </p>
      )}
      {run?.status === 'failed' && <ErrorNote message={`Run failed. ${run.error_message}`} />}
      {run?.status === 'blocked' && (
        <ErrorNote message={`Run blocked (${run.stop_reason}). Fix the project and try again.`} />
      )}
      {run && review && <ReviewView run={run} review={review} />}
    </div>
  )
}
