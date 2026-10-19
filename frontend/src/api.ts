import type { Preflight, Project, Review, Run, RunCreate } from './types'

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, init)
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // keep the status text when the body is not JSON
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function json(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export function artifactUrl(runId: string, relativePath: string): string {
  return `${BASE_URL}/runs/${runId}/artifact/${relativePath}`
}

// Page image URLs from the backend are absolute paths such as /api/runs/<id>/artifact/pages/...
export function absoluteUrl(path: string): string {
  const origin = new URL(BASE_URL).origin
  return path.startsWith('http') ? path : `${origin}${path}`
}

function encodePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/')
}

export const api = {
  listProjects: () => request<Project[]>('/projects'),
  createProject: (name: string) => request<Project>('/projects', json({ name })),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  uploadFiles: (id: string, files: File[]) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request<Project>(`/projects/${id}/upload`, { method: 'POST', body: form })
  },
  putFile: (id: string, path: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Project>(`/projects/${id}/files/${encodePath(path)}`, {
      method: 'PUT',
      body: form,
    })
  },
  removeFile: (id: string, path: string) =>
    request<Project>(`/projects/${id}/files/${encodePath(path)}`, { method: 'DELETE' }),
  preflight: (id: string, mainFile?: string | null) => {
    const query = mainFile ? `?main_file=${encodeURIComponent(mainFile)}` : ''
    return request<Preflight>(`/projects/${id}/preflight${query}`)
  },
  listRuns: (id: string) => request<Run[]>(`/projects/${id}/runs`),
  createRun: (id: string, payload: RunCreate) =>
    request<Run>(`/projects/${id}/runs`, json(payload)),
  getRun: (id: string) => request<Run>(`/runs/${id}`),
  getReview: (id: string) => request<Review>(`/runs/${id}/review`),
}
