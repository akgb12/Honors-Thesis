// Types matching the Django Ninja schemas and review payload from the backend

export type RunStatus = 'queued' | 'running' | 'blocked' | 'succeeded' | 'failed'
export type Effort = 'baseline' | 'low' | 'medium' | 'high'

export interface ProjectFile {
  id: number
  path: string
  size: number
  sha256: string
  uploaded_at: string
}

export interface Project {
  id: string
  name: string
  created_at: string
  updated_at: string
  files: ProjectFile[]
}

export interface PreflightIssue {
  code: string
  severity: string
  message: string
  source_file: string | null
  line: number | null
  dependency: string | null
}

export interface PreflightProblem {
  code: 'no_tex_files' | 'no_beamer_main' | 'choose_main_file'
  message: string
}

export interface Preflight {
  ok: boolean
  main_file: string | null
  main_candidates: string[]
  problem: PreflightProblem | null
  missing_images: string[]
  critical_blockers: string[]
  issues: PreflightIssue[]
}

export interface Run {
  id: string
  project_id: string
  status: RunStatus
  effort: Effort
  main_file: string
  seed_weak: string | null
  model_provider: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  storage_prefix: string
  stop_reason: string
  a_score: number | null
  f_score: number | null
  input_tokens: number
  output_tokens: number
  cost_usd: string
  error_message: string
}

export interface RunCreate {
  effort: Effort
  main_file?: string | null
  seed_weak?: string | null
}

export type ElementStatus =
  | 'done'
  | 'deterministic'
  | 'needs_description'
  | 'model_generated'
  | 'needs_review'
  | 'failed'
  | 'missing_asset'
  | 'not_handled'

// PDF points, origin bottom-left: x0, y0, x1, y1
export type Bbox = [number, number, number, number]
export type Anchor = [number, number]

export interface ReviewIssue {
  code: string
  message: string
  severity: string
  element_id: string | null
  details?: Record<string, unknown>
}

export interface HistoryEntry {
  round?: number
  by?: string
  change?: string
  model?: string | null
  input_tokens?: number
  output_tokens?: number
  cost_usd?: number
}

export interface ReviewElement {
  id: string
  type: string
  role: string | null
  text: string | null
  status: ElementStatus
  pages: number[]
  bbox: Bbox | null
  anchor: Anchor | null
  alt: string | null
  extended_description: string | null
  source: { file: string | null; line_start: number | null; line_end: number | null } | null
  history: HistoryEntry[]
  issues: ReviewIssue[]
}

export interface ReviewContainer {
  id: string
  kind: string
  element_ids: string[]
  rendered_pages: number[]
  title_element_id: string | null
}

export interface ReviewPage {
  number: number
  image_url: string
  width_points: number
  height_points: number
}

export interface Review {
  run_id: string
  containers: ReviewContainer[]
  elements: ReviewElement[]
  pages: ReviewPage[]
  scores: { accessibility: number | null; fidelity: number | null }
  stop_reason: string
  round_history: unknown[]
  issues: ReviewIssue[]
}
