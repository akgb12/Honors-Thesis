import type { ElementStatus } from './types'

interface StatusStyle {
  label: string
  color: string
  // SVG dash pattern so status never relies on color alone
  dash: string
}

export const STATUS_STYLES: Record<ElementStatus, StatusStyle> = {
  done: { label: 'Done', color: '#059669', dash: '' },
  deterministic: { label: 'Done', color: '#059669', dash: '' },
  model_generated: { label: 'Model generated', color: '#2563eb', dash: '' },
  needs_description: { label: 'Needs description', color: '#ea580c', dash: '7 4' },
  needs_review: { label: 'Needs review', color: '#b45309', dash: '2 3' },
  failed: { label: 'Failed', color: '#dc2626', dash: '10 3 2 3' },
  missing_asset: { label: 'Missing asset', color: '#9333ea', dash: '4 4' },
  not_handled: { label: 'Not handled', color: '#64748b', dash: '1 4' },
}

// Legend entries: deterministic is folded into done
export const LEGEND_STATUSES: ElementStatus[] = [
  'done',
  'model_generated',
  'needs_description',
  'needs_review',
  'failed',
  'missing_asset',
  'not_handled',
]

const FALLBACK: StatusStyle = { label: 'Unknown', color: '#64748b', dash: '' }

export function statusStyle(status: string): StatusStyle {
  return STATUS_STYLES[status as ElementStatus] ?? FALLBACK
}

export function statusColor(status: string): string {
  return statusStyle(status).color
}

export function statusLabel(status: string): string {
  return statusStyle(status).label
}

// deterministic elements are reported with done
export function statusGroup(status: string): ElementStatus {
  return status === 'deterministic' ? 'done' : (status as ElementStatus)
}

// Statuses a reviewer should look at first
export function needsAttention(status: string): boolean {
  return !['done', 'deterministic', 'model_generated'].includes(status)
}

const SEVERITY_ORDER = ['error', 'warning', 'info']

export function severityRank(severity: string): number {
  const index = SEVERITY_ORDER.indexOf(severity)
  return index === -1 ? SEVERITY_ORDER.length : index
}

export function isFinished(status: string): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'blocked'
}
