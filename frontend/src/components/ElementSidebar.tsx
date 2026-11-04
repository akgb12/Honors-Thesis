import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { shortElementId } from '../format'
import { severityRank, statusGroup, statusLabel } from '../status'
import type { ElementStatus, Review, ReviewElement, ReviewIssue } from '../types'
import { cx } from './classes'
import StatusSwatch from './StatusSwatch'
import { Badge } from './ui'

interface Props {
  review: Review
  elementsById: Map<string, ReviewElement>
  visible: Set<ElementStatus>
  pageNumber: number
  selectedId: string | null
  onSelect: (id: string) => void
  onGoToPage: (page: number) => void
  onShowAll: () => void
}

export default function ElementSidebar({
  review,
  elementsById,
  visible,
  pageNumber,
  selectedId,
  onSelect,
  onGoToPage,
  onShowAll,
}: Props) {
  const [tab, setTab] = useState<'elements' | 'issues'>('elements')
  const [scope, setScope] = useState<'page' | 'all'>('page')
  const [query, setQuery] = useState('')

  const issues = useMemo(() => {
    const all: ReviewIssue[] = [...review.issues, ...review.elements.flatMap((e) => e.issues)]
    return all.sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
  }, [review])

  const { groups, hidden } = useMemo(() => {
    const byContainer = new Map<string, ReviewElement[]>()
    for (const element of review.elements) {
      const key = element.id.split('/')[0]
      const list = byContainer.get(key) ?? []
      list.push(element)
      byContainer.set(key, list)
    }
    const needle = query.trim().toLowerCase()
    const result: { id: string; title: string; pages: number[]; elements: ReviewElement[] }[] = []
    let hidden = 0
    for (const container of review.containers) {
      if (scope === 'page' && !container.rendered_pages.includes(pageNumber)) continue
      const all = byContainer.get(container.id) ?? []
      hidden += all.filter((element) => !visible.has(statusGroup(element.status))).length
      const elements = all.filter((element) => {
        if (!visible.has(statusGroup(element.status))) return false
        if (!needle) return true
        return `${element.id} ${element.type} ${element.text ?? ''} ${element.alt ?? ''}`
          .toLowerCase()
          .includes(needle)
      })
      if (elements.length === 0) continue
      const title = container.title_element_id
        ? elementsById.get(container.title_element_id)?.text
        : null
      result.push({
        id: container.id,
        title: title ?? '',
        pages: container.rendered_pages,
        elements,
      })
    }
    return { groups: result, hidden }
  }, [review, elementsById, visible, scope, pageNumber, query])

  function openIssue(issue: ReviewIssue) {
    if (issue.element_id) {
      onSelect(issue.element_id)
      return
    }
    const page = issue.details?.page
    if (typeof page === 'number') onGoToPage(page)
  }

  const tabClass = (active: boolean) =>
    cx(
      'flex-1 border-b-2 px-3 py-2 text-sm font-medium',
      active
        ? 'border-brand-700 text-brand-800'
        : 'border-transparent text-slate-500 hover:text-slate-800',
    )

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div role="tablist" aria-label="Sidebar" className="flex border-b border-slate-200">
        <button
          role="tab"
          aria-selected={tab === 'elements'}
          className={tabClass(tab === 'elements')}
          onClick={() => setTab('elements')}
        >
          Elements
        </button>
        <button
          role="tab"
          aria-selected={tab === 'issues'}
          className={tabClass(tab === 'issues')}
          onClick={() => setTab('issues')}
        >
          Issues <span className="ml-1 rounded-full bg-slate-100 px-1.5 text-xs">{issues.length}</span>
        </button>
      </div>

      {tab === 'elements' ? (
        <>
          <div className="space-y-2 border-b border-slate-100 p-3">
            <label className="relative block">
              <span className="sr-only">Search elements</span>
              <Search
                aria-hidden
                className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400"
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search text, type or ID"
                className="w-full rounded-lg border border-slate-300 py-2 pl-8 pr-3 text-sm placeholder:text-slate-400"
              />
            </label>
            <div role="group" aria-label="Scope" className="flex gap-1 text-sm">
              {(['page', 'all'] as const).map((value) => (
                <button
                  key={value}
                  aria-pressed={scope === value}
                  onClick={() => setScope(value)}
                  className={cx(
                    'rounded-md px-2.5 py-1',
                    scope === value ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100',
                  )}
                >
                  {value === 'page' ? `Page ${pageNumber}` : 'All slides'}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-2">
            {groups.length === 0 && (
              <div className="p-3 text-sm text-slate-500">
                <p>
                  {query.trim()
                    ? 'No elements match your search.'
                    : hidden > 0
                      ? `Nothing needs attention ${scope === 'page' ? 'on this page' : 'here'}.`
                      : 'No elements here.'}
                </p>
                {hidden > 0 && (
                  <button
                    onClick={onShowAll}
                    className="mt-2 font-medium text-brand-700 underline hover:text-brand-800"
                  >
                    Show all {hidden} hidden element{hidden === 1 ? '' : 's'}
                  </button>
                )}
              </div>
            )}
            {groups.map((group) => (
              <section key={group.id} className="mb-3">
                <h3 className="sticky top-0 bg-white/95 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-slate-500 backdrop-blur">
                  {group.id.replace('_', ' ')}
                  {group.title && (
                    <span className="ml-1 font-normal normal-case tracking-normal text-slate-400">
                      · {group.title}
                    </span>
                  )}
                </h3>
                <ul>
                  {group.elements.map((element) => (
                    <li key={element.id}>
                      <button
                        onClick={() => onSelect(element.id)}
                        aria-current={element.id === selectedId}
                        className={cx(
                          'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm',
                          element.id === selectedId ? 'bg-brand-50 ring-1 ring-brand-200' : 'hover:bg-slate-50',
                        )}
                      >
                        <StatusSwatch status={element.status} size={16} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-slate-800">
                            {element.text ?? shortElementId(element.id)}
                          </span>
                          <span className="block truncate text-xs text-slate-400">
                            {element.type.replace(/_/g, ' ')} · {statusLabel(element.status)}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </>
      ) : (
        <ul className="min-h-0 flex-1 divide-y divide-slate-100 overflow-auto">
          {issues.length === 0 && <li className="p-4 text-sm text-slate-500">No issues found.</li>}
          {issues.map((issue, index) => {
            const clickable = Boolean(issue.element_id) || typeof issue.details?.page === 'number'
            return (
              <li key={`${issue.code}-${index}`}>
                <button
                  disabled={!clickable}
                  onClick={() => openIssue(issue)}
                  className="flex w-full flex-col gap-1 px-4 py-3 text-left text-sm hover:bg-slate-50 disabled:cursor-default disabled:hover:bg-transparent"
                >
                  <span className="flex items-center gap-2">
                    <Badge tone={issue.severity === 'error' ? 'danger' : 'warning'}>{issue.severity}</Badge>
                    {issue.element_id && (
                      <span className="truncate font-mono text-xs text-slate-400">{issue.element_id}</span>
                    )}
                  </span>
                  <span className="text-slate-700">{issue.message}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
