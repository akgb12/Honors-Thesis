const UNITS = ['B', 'KB', 'MB', 'GB']

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '–'
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1
  return `${value.toFixed(digits)} ${UNITS[unit]}`
}

const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

export function relativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  if (Number.isNaN(seconds)) return '–'
  if (Math.abs(seconds) < 45) return 'just now'
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit)
  }
  return formatter.format(Math.round(seconds / 60), 'minute')
}

export function formatDuration(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return minutes > 0 ? `${minutes}m ${seconds.toString().padStart(2, '0')}s` : `${seconds}s`
}

export function formatCost(value: string | number): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '–'
  return amount === 0 ? '$0.00' : `$${amount.toFixed(amount < 0.01 ? 4 : 2)}`
}

export type ScoreTone = 'success' | 'warning' | 'danger'

export function scoreTone(score: number | null): ScoreTone {
  if (score === null) return 'warning'
  if (score >= 90) return 'success'
  if (score >= 60) return 'warning'
  return 'danger'
}

export function fileKind(path: string): 'tex' | 'pdf' | 'image' | 'style' | 'other' {
  const extension = path.split('.').pop()?.toLowerCase() ?? ''
  if (extension === 'tex') return 'tex'
  if (extension === 'pdf') return 'pdf'
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'eps', 'webp'].includes(extension)) return 'image'
  if (['sty', 'cls', 'bst', 'bib'].includes(extension)) return 'style'
  return 'other'
}

export function shortElementId(id: string): string {
  const parts = id.split('/')
  return parts[parts.length - 1] || id
}
