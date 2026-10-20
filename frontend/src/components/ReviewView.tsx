import { useMemo, useState } from 'react'
import { needsAttention, statusGroup } from '../status'
import type { ElementStatus, Review, ReviewElement, Run } from '../types'
import ElementSidebar from './ElementSidebar'
import Inspector from './Inspector'
import PageViewer from './PageViewer'
import ReviewSummary from './ReviewSummary'
import StatusFilter from './StatusFilter'

const DEFAULT_HIDDEN: ElementStatus = 'done'

export default function ReviewView({ run, review }: { run: Run; review: Review }) {
  const [pageNumber, setPageNumber] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [visible, setVisible] = useState<Set<ElementStatus>>(() => {
    const all = new Set<ElementStatus>()
    for (const element of review.elements) all.add(statusGroup(element.status))
    all.delete(DEFAULT_HIDDEN)
    return all
  })

  const elementsById = useMemo(() => {
    const map = new Map<string, ReviewElement>()
    for (const element of review.elements) map.set(element.id, element)
    return map
  }, [review])

  const counts = useMemo(() => {
    const result: Partial<Record<ElementStatus, number>> = {}
    for (const element of review.elements) {
      const group = statusGroup(element.status)
      result[group] = (result[group] ?? 0) + 1
    }
    return result
  }, [review])

  const flaggedPages = useMemo(() => {
    const pages = new Set<number>()
    for (const element of review.elements) {
      if (needsAttention(element.status)) element.pages.forEach((page) => pages.add(page))
    }
    return pages
  }, [review])

  const attentionCount = review.elements.filter((element) => needsAttention(element.status)).length
  const pageElements = review.elements.filter(
    (element) => element.pages.includes(pageNumber) && visible.has(statusGroup(element.status)),
  )
  const selected = selectedId ? (elementsById.get(selectedId) ?? null) : null

  function toggle(status: ElementStatus) {
    setVisible((current) => {
      const next = new Set(current)
      if (next.has(status)) next.delete(status)
      else next.add(status)
      return next
    })
  }

  function select(id: string) {
    setSelectedId(id)
    const element = elementsById.get(id)
    if (element) {
      // Unmapped elements fall back to the first page of their slide
      const container = review.containers.find((item) => item.id === id.split('/')[0])
      const pages = element.pages.length > 0 ? element.pages : (container?.rendered_pages ?? [])
      if (pages.length > 0 && !pages.includes(pageNumber)) setPageNumber(pages[0])
    }
    // A selected element should always be visible on the slide
    if (element) {
      const group = statusGroup(element.status)
      setVisible((current) => (current.has(group) ? current : new Set(current).add(group)))
    }
  }

  return (
    <div className="space-y-5">
      <ReviewSummary run={run} attentionCount={attentionCount} />

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Show on slides</h2>
        <StatusFilter counts={counts} visible={visible} onToggle={toggle} />
      </div>

      <div className="grid gap-4 lg:h-[calc(100vh-9rem)] lg:min-h-[34rem] lg:grid-cols-[19rem_minmax(0,1fr)_23rem]">
        <aside
          aria-label="Elements and issues"
          className="h-96 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:h-auto"
        >
          <ElementSidebar
            review={review}
            elementsById={elementsById}
            visible={visible}
            pageNumber={pageNumber}
            selectedId={selectedId}
            onSelect={select}
            onGoToPage={setPageNumber}
            onShowAll={() => setVisible(new Set(Object.keys(counts) as ElementStatus[]))}
          />
        </aside>

        <section
          aria-label="Slide preview"
          className="h-[36rem] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:h-auto"
        >
          <PageViewer
            pages={review.pages}
            pageNumber={pageNumber}
            elements={pageElements}
            flaggedPages={flaggedPages}
            selectedId={selectedId}
            onSelect={select}
            onPage={setPageNumber}
          />
        </section>

        <aside
          aria-label="Inspector"
          className="overflow-auto rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
        >
          <h2 className="mb-3 text-sm font-semibold text-slate-700">Inspector</h2>
          <Inspector element={selected} />
        </aside>
      </div>
    </div>
  )
}
