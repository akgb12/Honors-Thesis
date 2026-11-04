import { ChevronRight, FolderOpen, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Alert, Button, Card, EmptyState, PageHeader, Skeleton } from '../components/ui'
import { errorMessage } from '../errors'
import { relativeTime } from '../format'
import type { Project } from '../types'

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listProjects()
      .then(setProjects)
      .catch((e) => setError(errorMessage(e)))
  }, [])

  async function create(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    try {
      const project = await api.createProject(name.trim())
      setProjects((current) => [project, ...(current ?? [])])
      setName('')
      setError(null)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setCreating(false)
    }
  }

  async function remove(project: Project) {
    if (!window.confirm(`Delete “${project.name}” and all of its files and runs?`)) return
    try {
      await api.deleteProject(project.id)
      setProjects((current) => (current ?? []).filter((item) => item.id !== project.id))
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <div>
      <PageHeader
        title="Projects"
        subtitle="Upload Beamer slides and get back accessible LaTeX, a tagged PDF and a review report."
      />

      <Card className="mb-6">
        <form onSubmit={create} className="flex flex-wrap items-end gap-3">
          <label className="min-w-64 flex-1 text-sm font-medium text-slate-700">
            New project name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. CSCE 421 Lecture 1"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm placeholder:text-slate-400"
            />
          </label>
          <Button
            type="submit"
            variant="primary"
            loading={creating}
            disabled={!name.trim()}
            icon={<Plus aria-hidden className="h-4 w-4" />}
          >
            Create project
          </Button>
        </form>
      </Card>

      {error && (
        <div className="mb-4">
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        </div>
      )}

      {projects === null && !error && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((key) => (
            <Skeleton key={key} className="h-24" />
          ))}
        </div>
      )}

      {projects?.length === 0 && (
        <EmptyState icon={<FolderOpen aria-hidden className="h-6 w-6" />} title="No projects yet">
          Create your first project above, then upload a .zip of your Beamer slides.
        </EmptyState>
      )}

      {projects && projects.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((project) => (
            <li
              key={project.id}
              className="group relative rounded-xl border border-slate-200 bg-white shadow-sm transition hover:border-brand-300 hover:shadow-md"
            >
              <Link to={`/projects/${project.id}`} className="flex items-center gap-4 rounded-xl p-4">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                  <FolderOpen aria-hidden className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-slate-900">{project.name}</span>
                  <span className="block text-sm text-slate-500">
                    {project.files.length} {project.files.length === 1 ? 'file' : 'files'} · updated{' '}
                    {relativeTime(project.updated_at)}
                  </span>
                </span>
                <ChevronRight aria-hidden className="h-5 w-5 text-slate-300 group-hover:text-brand-600" />
              </Link>
              <button
                type="button"
                onClick={() => remove(project)}
                aria-label={`Delete ${project.name}`}
                className="absolute right-2 top-2 rounded-md p-1.5 text-slate-300 opacity-0 transition hover:bg-red-50 hover:text-red-600 focus-visible:opacity-100 group-hover:opacity-100"
              >
                <Trash2 aria-hidden className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
