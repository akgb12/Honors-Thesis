import { useMemo, useState } from 'react'
import { artifactUrl } from '../api'
import { LEGEND_STATUSES, STATUS_LABELS, severityRank, statusColor } from '../status'
import type { Review, ReviewElement, Run } from '../types'
import Inspector from './Inspector'
import PageOverlay from './PageOverlay'

interface Props {
  run: Run
  review: Review
}

export default function ReviewView({ run, review }: Props) {
  const [pageNumber, setPageNumber] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const elementsById = useMemo(() => {
    const map = new Map<string, ReviewElement>()
    for (const element of review.elements) map.set(element.id, element)
    return map
  }, [review])

  const allIssues = useMemo(() => {
    const issues = [...review.issues, ...review.elements.flatMap((element) => element.issues)]
    return issues.sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
  }, [review])

  const page = review.pages.find((candidate) => candidate.number === pageNumber) ?? review.pages[0]
  const pageElements = review.elements.filter((element) => element.pages.includes(pageNumber))
  const selected = selectedId ? (elementsById.get(selectedId) ?? null) : null

  function select(id: string) {
    setSelectedId(id)
    const element = elementsById.get(id)
    if (element && element.pages.length > 0 && !element.pages.includes(pageNumber)) {
      setPageNumber(element.pages[0])
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 rounded border border-gray-200 bg-white px-3 py-2 text-sm">
        <span>
          A (preliminary): <strong>{run.a_score?.toFixed(1) ?? '–'}</strong>
        </span>
        <span>
          F (preliminary): <strong>{run.f_score?.toFixed(1) ?? '–'}</strong>
        </span>
        <span>Cost: ${Number(run.cost_usd).toFixed(4)}</span>
        <span>
          Tokens: {run.input_tokens} in / {run.output_tokens} out
        </span>
        <span>Stop reason: {run.stop_reason || '–'}</span>
        <span className="flex gap-3">
          <a className="text-blue-700 hover:underline" href={artifactUrl(run.id, 'output/tagged.pdf')}>
            Tagged PDF
          </a>
          <a
            className="text-blue-700 hover:underline"
            href={artifactUrl(run.id, 'output/updated_project.zip')}
          >
            Updated project (.zip)
          </a>
          <a className="text-blue-700 hover:underline" href={artifactUrl(run.id, 'report.html')}>
            report.html
          </a>
        </span>
      </div>

      <ul className="flex flex-wrap gap-3 text-xs" aria-label="Status legend">
        {LEGEND_STATUSES.map((status) => (
          <li key={status} className="flex items-center gap-1">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ backgroundColor: statusColor(status) }}
            />
            {STATUS_LABELS[status]}
          </li>
        ))}
      </ul>

      <div className="grid gap-3 lg:grid-cols-[20rem_1fr_22rem]">
        <aside className="max-h-[75vh] space-y-4 overflow-auto rounded border border-gray-200 bg-white p-3">
          <section>
            <h2 className="mb-1 font-semibold">Issues ({allIssues.length})</h2>
            {allIssues.length === 0 && <p className="text-sm text-gray-500">No issues.</p>}
            <ul className="space-y-1 text-sm">
              {allIssues.map((issue, index) => (
                <li key={`${issue.code}-${index}`}>
                  <button
                    className="text-left hover:underline"
                    disabled={!issue.element_id}
                    onClick={() => issue.element_id && select(issue.element_id)}
                  >
                    <span className="font-medium">{issue.severity}</span>: {issue.message}
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="mb-1 font-semibold">Elements by slide</h2>
            <ul className="space-y-2 text-sm">
              {review.containers.map((container) => (
                <li key={container.id}>
                  <div className="font-medium">{container.id}</div>
                  <ul className="ml-3">
                    {container.element_ids.map((id) => {
                      const element = elementsById.get(id)
                      if (!element) return null
                      return (
                        <li key={id}>
                          <button
                            onClick={() => select(id)}
                            className={`flex items-center gap-1 text-left hover:underline ${
                              id === selectedId ? 'font-semibold' : ''
                            }`}
                          >
                            <span
                              className="inline-block h-2 w-2 shrink-0 rounded-full"
                              style={{ backgroundColor: statusColor(element.status) }}
                            />
                            {id.split('/').slice(1).join('/') || id}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          </section>
        </aside>

        <section className="space-y-2 overflow-auto">
          <div className="flex items-center gap-2 text-sm">
            <button
              className="rounded border border-gray-300 bg-white px-2 py-1 disabled:opacity-50"
              disabled={pageNumber <= 1}
              onClick={() => setPageNumber(pageNumber - 1)}
            >
              Previous
            </button>
            <span>
              Page {pageNumber} of {review.pages.length}
            </span>
            <button
              className="rounded border border-gray-300 bg-white px-2 py-1 disabled:opacity-50"
              disabled={pageNumber >= review.pages.length}
              onClick={() => setPageNumber(pageNumber + 1)}
            >
              Next
            </button>
          </div>
          {page && (
            <PageOverlay
              page={page}
              elements={pageElements}
              selectedId={selectedId}
              onSelect={select}
            />
          )}
        </section>

        <aside className="max-h-[75vh] overflow-auto rounded border border-gray-200 bg-white p-3">
          <h2 className="mb-2 font-semibold">Inspector</h2>
          <Inspector element={selected} />
        </aside>
      </div>
    </div>
  )
}
