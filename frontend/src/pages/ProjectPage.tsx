import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import ErrorNote from '../components/ErrorNote'
import { errorMessage } from '../errors'
import PreflightPanel from '../components/PreflightPanel'
import type { Effort, Preflight, Project, Run } from '../types'

export default function ProjectPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [preflight, setPreflight] = useState<Preflight | null>(null)
  const [runs, setRuns] = useState<Run[]>([])
  const [effort, setEffort] = useState<Effort>('medium')
  const [seedWeak, setSeedWeak] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refreshPreflight = useCallback(async () => {
    try {
      setPreflight(await api.preflight(id))
    } catch (e) {
      setPreflight(null)
      setError(errorMessage(e))
    }
  }, [id])

  useEffect(() => {
    api
      .getProject(id)
      .then((value) => {
        setProject(value)
        if (value.files.length > 0) void refreshPreflight()
      })
      .catch((e) => setError(errorMessage(e)))
    api
      .listRuns(id)
      .then(setRuns)
      .catch((e) => setError(errorMessage(e)))
  }, [id, refreshPreflight])

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    if (files.length === 0) return
    setBusy(true)
    try {
      setProject(await api.uploadFiles(id, files))
      setError(null)
      await refreshPreflight()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
      event.target.value = ''
    }
  }

  async function fillSlot(path: string, file: File) {
    setBusy(true)
    try {
      setProject(await api.putFile(id, path, file))
      setError(null)
      await refreshPreflight()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function startRun(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      const run = await api.createRun(id, {
        effort,
        seed_weak: seedWeak.trim() || null,
      })
      navigate(`/runs/${run.id}`)
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  if (!project) return error ? <ErrorNote message={error} /> : <p>Loading…</p>

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-blue-700 hover:underline">
          ← Projects
        </Link>
        <h1 className="text-2xl font-semibold">{project.name}</h1>
      </div>
      <ErrorNote message={error} />

      <section className="space-y-2 rounded border border-gray-200 bg-white p-3">
        <h2 className="font-semibold">Files</h2>
        <label className="block text-sm">
          Upload a project .zip or individual files
          <input type="file" multiple onChange={upload} disabled={busy} className="mt-1 block" />
        </label>
        <ul className="text-sm text-gray-700">
          {project.files.map((file) => (
            <li key={file.id}>
              {file.path} <span className="text-gray-400">({file.size} bytes)</span>
            </li>
          ))}
          {project.files.length === 0 && <li className="text-gray-500">No files yet.</li>}
        </ul>
      </section>

      {project.files.length > 0 && (
        <PreflightPanel preflight={preflight} busy={busy} onFill={fillSlot} onRecheck={refreshPreflight} />
      )}

      <section className="rounded border border-gray-200 bg-white p-3">
        <h2 className="mb-2 font-semibold">Start a run</h2>
        <form onSubmit={startRun} className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            Effort
            <select
              value={effort}
              onChange={(e) => setEffort(e.target.value as Effort)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
          <label className="text-sm">
            Seed weak description (element ID, demo only)
            <input
              value={seedWeak}
              onChange={(e) => setSeedWeak(e.target.value)}
              placeholder="slide_04/figure_01"
              className="mt-1 block w-64 rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <button
            type="submit"
            disabled={busy || !preflight?.ok}
            className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
          >
            Start run
          </button>
        </form>
      </section>

      <section className="rounded border border-gray-200 bg-white p-3">
        <h2 className="mb-2 font-semibold">Runs</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-gray-500">
            <tr>
              <th className="py-1">Started</th>
              <th>Status</th>
              <th>Effort</th>
              <th>A</th>
              <th>F</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-t border-gray-100">
                <td className="py-1">
                  <Link to={`/runs/${run.id}`} className="text-blue-700 hover:underline">
                    {new Date(run.created_at).toLocaleString()}
                  </Link>
                </td>
                <td>{run.status}</td>
                <td>{run.effort}</td>
                <td>{run.a_score?.toFixed(1) ?? '–'}</td>
                <td>{run.f_score?.toFixed(1) ?? '–'}</td>
                <td>${Number(run.cost_usd).toFixed(4)}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={6} className="py-1 text-gray-500">
                  No runs yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  )
}
