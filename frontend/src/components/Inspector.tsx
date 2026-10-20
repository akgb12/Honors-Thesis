import { MousePointerClick } from 'lucide-react'
import { formatCost } from '../format'
import { statusColor, statusLabel } from '../status'
import type { ReviewElement } from '../types'
import StatusSwatch from './StatusSwatch'
import { Badge } from './ui'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800">{children}</dd>
    </div>
  )
}

export default function Inspector({ element }: { element: ReviewElement | null }) {
  if (!element) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-4 py-10 text-center text-sm text-slate-500">
        <MousePointerClick aria-hidden className="h-6 w-6 text-slate-300" />
        Select an element from the list or click one on the slide to inspect it.
      </div>
    )
  }
  const source = element.source
  return (
    <div className="space-y-5">
      <div>
        <p className="break-all font-mono text-xs text-slate-500">{element.id}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Badge tone="neutral" className="capitalize">
            {element.type.replace(/_/g, ' ')}
          </Badge>
          <span
            className="inline-flex items-center gap-1.5 rounded-full bg-white px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-slate-200"
            style={{ color: statusColor(element.status) }}
          >
            <StatusSwatch status={element.status} size={16} />
            {statusLabel(element.status)}
          </span>
        </div>
      </div>

      {element.text && (
        <blockquote className="rounded-lg border-l-4 border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          {element.text}
        </blockquote>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Field label="PDF role">{element.role ?? '–'}</Field>
        <Field label="Pages">{element.pages.length > 0 ? element.pages.join(', ') : '–'}</Field>
        <Field label="Source">
          {source?.file ? (
            <span className="font-mono text-xs">
              {source.file}:{source.line_start}
              {source.line_end !== source.line_start ? `–${source.line_end}` : ''}
            </span>
          ) : (
            '–'
          )}
        </Field>
      </dl>

      <div className="space-y-3">
        <label className="block">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-400">Alt text</span>
          <textarea
            readOnly
            value={element.alt ?? ''}
            placeholder="No alt text"
            rows={4}
            className="mt-1 block w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400"
          />
        </label>
        {element.extended_description && (
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Extended description
            </span>
            <textarea
              readOnly
              value={element.extended_description}
              rows={4}
              className="mt-1 block w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
            />
          </label>
        )}
        <p className="text-xs text-slate-400">Read-only in Mark 1. Editing comes in a later version.</p>
      </div>

      <section>
        <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
          Issues ({element.issues.length})
        </h3>
        {element.issues.length === 0 ? (
          <p className="text-sm text-slate-500">None.</p>
        ) : (
          <ul className="space-y-2">
            {element.issues.map((issue, index) => (
              <li key={`${issue.code}-${index}`} className="flex gap-2 text-sm text-slate-700">
                <Badge tone={issue.severity === 'error' ? 'danger' : 'warning'}>{issue.severity}</Badge>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">History</h3>
        {element.history.length === 0 ? (
          <p className="text-sm text-slate-500">No changes recorded.</p>
        ) : (
          <ol className="relative space-y-3 border-l border-slate-200 pl-4">
            {element.history.map((entry, index) => (
              <li key={index} className="relative text-sm">
                <span
                  aria-hidden
                  className="absolute -left-[1.3rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand-600"
                />
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-slate-800">Round {entry.round ?? 0}</span>
                  <Badge tone={entry.by === 'model' ? 'info' : 'neutral'}>{entry.by ?? 'unknown'}</Badge>
                  {entry.model && <span className="font-mono text-xs text-slate-400">{entry.model}</span>}
                </div>
                {entry.change && <p className="text-slate-600">{entry.change}</p>}
                {(entry.input_tokens || entry.output_tokens) && (
                  <p className="text-xs text-slate-400">
                    {entry.input_tokens ?? 0} in · {entry.output_tokens ?? 0} out ·{' '}
                    {formatCost(entry.cost_usd ?? 0)}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}
