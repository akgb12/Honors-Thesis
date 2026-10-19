import { ArrowLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import ReviewView from '../components/ReviewView'
import { buttonClasses } from '../components/classes'
import { Alert, Card, PageHeader, RunStatusBadge, Skeleton, Spinner } from '../components/ui'
import { errorMessage } from '../errors'
import { formatDuration, relativeTime } from '../format'
import { isFinished } from '../status'
import type { Review, Run } from '../types'

const POLL_MS = 2000

function Elapsed({ since }: { since: string }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return <>{formatDuration(now - new Date(since).getTime())}</>
}

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

  if (error && !run) {
    return (
      <Alert tone="danger" title="Could not load this run">
        {error}
      </Alert>
    )
  }

  if (!run) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-40" />
      </div>
    )
  }

  const backToProject = (
    <Link to={`/projects/${run.project_id}`} className={buttonClasses('secondary', 'sm')}>
      <ArrowLeft aria-hidden className="h-4 w-4" /> Back to project
    </Link>
  )

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: 'Projects', to: '/' },
          { label: 'Project', to: `/projects/${run.project_id}` },
          { label: 'Run' },
        ]}
        title={
          <span className="flex items-center gap-3">
            Run results <RunStatusBadge status={run.status} />
          </span>
        }
        subtitle={
          <>
            <span className="capitalize">{run.effort}</span> effort
            {run.main_file && (
              <>
                {' · '}
                <span className="font-mono">{run.main_file}</span>
              </>
            )}
            {' · started '}
            {relativeTime(run.created_at)}
          </>
        }
        actions={backToProject}
      />

      {error && (
        <div className="mb-4">
          <Alert tone="danger">{error}</Alert>
        </div>
      )}

      {!isFinished(run.status) && (
        <Card>
          <div role="status" aria-live="polite" className="py-6 text-center">
            <Spinner className="mx-auto h-8 w-8 text-brand-700" />
            <p className="mt-3 text-base font-semibold text-slate-900">
              {run.status === 'queued' ? 'Waiting for a worker…' : 'Making your slides accessible…'}
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Compiling, finding figures, writing descriptions and tagging the PDF. Large decks can
              take a few minutes.
            </p>
            <div className="mx-auto mt-4 h-1.5 w-64 overflow-hidden rounded-full bg-slate-100">
              <div className="animate-indeterminate h-full w-1/4 rounded-full bg-brand-600" />
            </div>
            <p className="mt-2 text-xs text-slate-400">
              Elapsed <Elapsed since={run.started_at ?? run.created_at} />
            </p>
          </div>
        </Card>
      )}

      {run.status === 'failed' && (
        <Alert tone="danger" title="The run failed" action={backToProject}>
          {run.error_message || 'The pipeline stopped unexpectedly. Check the worker log for details.'}
        </Alert>
      )}

      {run.status === 'blocked' && (
        <Alert tone="warning" title="The run was blocked before it started" action={backToProject}>
          Reason: {run.stop_reason.replace(/_/g, ' ') || 'pre-flight check failed'}. Fix the project
          and start a new run.
        </Alert>
      )}

      {run.status === 'succeeded' && !review && !error && <Skeleton className="h-96" />}
      {run.status === 'succeeded' && review && <ReviewView run={run} review={review} />}
    </div>
  )
}
