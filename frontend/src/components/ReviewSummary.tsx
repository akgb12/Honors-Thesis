import { Download, FileArchive, FileText, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { artifactUrl } from '../api'
import { formatCost, scoreTone } from '../format'
import type { Run } from '../types'
import { buttonClasses } from './classes'
import { Badge, Meter } from './ui'

function ScoreTile({ label, hint, value }: { label: string; hint: string; value: number | null }) {
  const tone = scoreTone(value)
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-slate-600">{label}</span>
        <Badge tone="neutral">preliminary</Badge>
      </div>
      <div className="mt-1 text-3xl font-bold tracking-tight text-slate-900">
        {value === null ? '–' : value.toFixed(1)}
        <span className="text-base font-medium text-slate-400"> / 100</span>
      </div>
      <div className="mt-2">
        <Meter value={value} label={label} tone={tone} />
      </div>
      <p className="mt-2 text-xs text-slate-500">{hint}</p>
    </div>
  )
}

function InfoTile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <span className="text-sm font-medium text-slate-600">{label}</span>
      <div className="mt-1 text-2xl font-bold tracking-tight text-slate-900">{value}</div>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  )
}

export default function ReviewSummary({
  run,
  attentionCount,
}: {
  run: Run
  attentionCount: number
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <ScoreTile label="Accessibility (A)" hint="How well a screen reader can use the PDF" value={run.a_score} />
        <ScoreTile label="Fidelity (F)" hint="How closely the output matches your slides" value={run.f_score} />
        <InfoTile
          label="Needs attention"
          value={
            <span className="flex items-center gap-2">
              {attentionCount}
              {attentionCount > 0 && <TriangleAlert aria-hidden className="h-5 w-5 text-amber-500" />}
            </span>
          }
          sub={attentionCount === 0 ? 'Nothing to review' : 'Elements to review; shown on the slides'}
        />
        <InfoTile
          label="Model cost"
          value={formatCost(run.cost_usd)}
          sub={`${run.input_tokens.toLocaleString()} in · ${run.output_tokens.toLocaleString()} out tokens · ${run.model_provider}`}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <p className="text-sm text-slate-600">
          Stopped because <Badge tone="brand">{run.stop_reason.replace(/_/g, ' ') || 'unknown'}</Badge>
        </p>
        <div className="flex flex-wrap gap-2">
          <a className={buttonClasses('primary', 'sm')} href={artifactUrl(run.id, 'output/tagged.pdf')}>
            <Download aria-hidden className="h-4 w-4" /> Tagged PDF
          </a>
          <a
            className={buttonClasses('secondary', 'sm')}
            href={artifactUrl(run.id, 'output/updated_project.zip')}
          >
            <FileArchive aria-hidden className="h-4 w-4" /> Updated project (.zip)
          </a>
          <a
            className={buttonClasses('secondary', 'sm')}
            href={artifactUrl(run.id, 'report.html')}
            target="_blank"
            rel="noreferrer"
          >
            <FileText aria-hidden className="h-4 w-4" /> Report
          </a>
        </div>
      </div>
    </div>
  )
}
