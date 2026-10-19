import { STATUS_LABELS, statusColor } from '../status'
import type { ReviewElement } from '../types'

export default function Inspector({ element }: { element: ReviewElement | null }) {
  if (!element) return <p className="text-sm text-gray-500">Select an element to inspect it.</p>
  const source = element.source
  return (
    <div className="space-y-3 text-sm">
      <h3 className="break-all font-semibold">{element.id}</h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-gray-500">Type</dt>
        <dd>{element.type}</dd>
        <dt className="text-gray-500">Role</dt>
        <dd>{element.role ?? '–'}</dd>
        <dt className="text-gray-500">Status</dt>
        <dd>
          <span
            className="inline-block rounded px-2 text-white"
            style={{ backgroundColor: statusColor(element.status) }}
          >
            {STATUS_LABELS[element.status] ?? element.status}
          </span>
        </dd>
        <dt className="text-gray-500">Source</dt>
        <dd>
          {source?.file ? `${source.file}:${source.line_start}–${source.line_end}` : '–'}
        </dd>
        <dt className="text-gray-500">Pages</dt>
        <dd>{element.pages.length > 0 ? element.pages.join(', ') : '–'}</dd>
      </dl>

      <label className="block">
        <span className="text-gray-500">Alt text (read-only; editing comes later)</span>
        <textarea
          readOnly
          value={element.alt ?? ''}
          rows={3}
          className="mt-1 w-full rounded border border-gray-300 bg-gray-50 px-2 py-1"
        />
      </label>
      <label className="block">
        <span className="text-gray-500">Extended description (read-only)</span>
        <textarea
          readOnly
          value={element.extended_description ?? ''}
          rows={3}
          className="mt-1 w-full rounded border border-gray-300 bg-gray-50 px-2 py-1"
        />
      </label>

      <div>
        <h4 className="font-medium">Issues</h4>
        {element.issues.length === 0 && <p className="text-gray-500">None</p>}
        <ul className="list-disc pl-5">
          {element.issues.map((issue, index) => (
            <li key={`${issue.code}-${index}`}>
              <span className="font-medium">{issue.severity}</span>: {issue.message}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h4 className="font-medium">History</h4>
        {element.history.length === 0 && <p className="text-gray-500">None</p>}
        <ul className="space-y-1">
          {element.history.map((entry, index) => (
            <li key={index} className="rounded border border-gray-200 px-2 py-1">
              round {entry.round ?? 0} · {entry.by ?? '?'}
              {entry.model ? ` · ${entry.model}` : ''}
              <br />
              {entry.change}
              <br />
              <span className="text-gray-500">
                {entry.input_tokens ?? 0} in / {entry.output_tokens ?? 0} out tokens · $
                {(entry.cost_usd ?? 0).toFixed(4)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
