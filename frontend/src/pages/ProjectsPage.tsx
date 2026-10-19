import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import ErrorNote from '../components/ErrorNote'
import { errorMessage } from '../errors'
import type { Project } from '../types'

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [name, setName] = useState('')
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
    try {
      const project = await api.createProject(name.trim())
      setProjects((current) => [project, ...(current ?? [])])
      setName('')
      setError(null)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Projects</h1>
      <form onSubmit={create} className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New project name"
          aria-label="New project name"
          className="w-72 rounded border border-gray-300 px-2 py-1"
        />
        <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-white">
          Create
        </button>
      </form>
      <ErrorNote message={error} />
      {projects === null && !error && <p>Loading…</p>}
      <ul className="divide-y divide-gray-200 rounded border border-gray-200 bg-white">
        {projects?.map((project) => (
          <li key={project.id} className="flex items-center justify-between px-3 py-2">
            <Link to={`/projects/${project.id}`} className="font-medium text-blue-700 hover:underline">
              {project.name}
            </Link>
            <span className="text-sm text-gray-500">
              {project.files.length} files · {new Date(project.created_at).toLocaleString()}
            </span>
          </li>
        ))}
        {projects?.length === 0 && <li className="px-3 py-2 text-gray-500">No projects yet.</li>}
      </ul>
    </div>
  )
}
