import type { ElementStatus } from './types'

export const STATUS_COLORS: Record<ElementStatus, string> = {
  done: '#15803d',
  deterministic: '#15803d',
  model_generated: '#2563eb',
  needs_review: '#d97706',
  failed: '#dc2626',
  missing_asset: '#9333ea',
  not_handled: '#6b7280',
}

export const STATUS_LABELS: Record<ElementStatus, string> = {
  done: 'Done / deterministic',
  deterministic: 'Deterministic',
  model_generated: 'Model generated',
  needs_review: 'Needs review',
  failed: 'Failed',
  missing_asset: 'Missing asset',
  not_handled: 'Not handled',
}

// Legend entries: deterministic is folded into done
export const LEGEND_STATUSES: ElementStatus[] = [
  'done',
  'model_generated',
  'needs_review',
  'failed',
  'missing_asset',
  'not_handled',
]

export function statusColor(status: string): string {
  return STATUS_COLORS[status as ElementStatus] ?? '#6b7280'
}

const SEVERITY_ORDER = ['error', 'warning', 'info']

export function severityRank(severity: string): number {
  const index = SEVERITY_ORDER.indexOf(severity)
  return index === -1 ? SEVERITY_ORDER.length : index
}

export function isFinished(status: string): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'blocked'
}
