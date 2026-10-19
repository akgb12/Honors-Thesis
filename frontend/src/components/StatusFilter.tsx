import { LEGEND_STATUSES, statusLabel } from '../status'
import type { ElementStatus } from '../types'
import { cx } from './classes'
import StatusSwatch from './StatusSwatch'

export default function StatusFilter({
  counts,
  visible,
  onToggle,
}: {
  counts: Partial<Record<ElementStatus, number>>
  visible: Set<ElementStatus>
  onToggle: (status: ElementStatus) => void
}) {
  return (
    <div role="group" aria-label="Show elements by status" className="flex flex-wrap gap-2">
      {LEGEND_STATUSES.map((status) => {
        const count = counts[status] ?? 0
        const on = visible.has(status)
        return (
          <button
            key={status}
            type="button"
            aria-pressed={on}
            disabled={count === 0}
            onClick={() => onToggle(status)}
            className={cx(
              'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-40',
              on
                ? 'border-slate-300 bg-white text-slate-800 shadow-sm'
                : 'border-transparent bg-slate-100 text-slate-500 hover:bg-slate-200',
            )}
          >
            <StatusSwatch status={status} />
            {statusLabel(status)}
            <span className="rounded-full bg-slate-100 px-1.5 text-xs font-medium text-slate-600">
              {count}
            </span>
          </button>
        )
      })}
    </div>
  )
}
