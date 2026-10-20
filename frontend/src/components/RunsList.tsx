import { History } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatCost, relativeTime, scoreTone } from '../format'
import type { Run } from '../types'
import { Card, RunStatusBadge } from './ui'
import { cx } from './classes'

const SCORE_TEXT = {
  success: 'text-emerald-700',
  warning: 'text-amber-700',
  danger: 'text-red-700',
}

function Score({ label, value }: { label: string; value: number | null }) {
  return (
    <span className="text-xs text-slate-500">
      {label}{' '}
      <span className={cx('text-sm font-semibold', value !== null && SCORE_TEXT[scoreTone(value)])}>
        {value === null ? '–' : value.toFixed(1)}
      </span>
    </span>
  )
}

export default function RunsList({ runs }: { runs: Run[] }) {
  return (
    <Card title="Runs" description="Newest first" flush>
      {runs.length === 0 ? (
        <div className="flex flex-col items-center px-5 pb-6 pt-2 text-center text-sm text-slate-500">
          <History aria-hidden className="mb-2 h-6 w-6 text-slate-300" />
          No runs yet. Finish the steps on the left to start one.
        </div>
      ) : (
        <ul className="divide-y divide-slate-100">
          {runs.map((run) => (
            <li key={run.id}>
              <Link to={`/runs/${run.id}`} className="block px-5 py-3 hover:bg-slate-50">
                <div className="flex items-center justify-between gap-2">
                  <RunStatusBadge status={run.status} />
                  <span className="text-xs text-slate-400">{relativeTime(run.created_at)}</span>
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5">
                  <span className="text-xs capitalize text-slate-500">{run.effort}</span>
                  <Score label="A" value={run.a_score} />
                  <Score label="F" value={run.f_score} />
                  <span className="text-xs text-slate-500">{formatCost(run.cost_usd)}</span>
                </div>
                {run.main_file && (
                  <div className="mt-1 truncate font-mono text-xs text-slate-400">{run.main_file}</div>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
