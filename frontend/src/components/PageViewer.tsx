import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { absoluteUrl } from '../api'
import type { ReviewElement, ReviewPage } from '../types'
import { cx } from './classes'
import PageOverlay from './PageOverlay'
import { Button } from './ui'

interface Props {
  pages: ReviewPage[]
  pageNumber: number
  elements: ReviewElement[]
  flaggedPages: Set<number>
  selectedId: string | null
  onSelect: (id: string) => void
  onPage: (page: number) => void
}

export default function PageViewer({
  pages,
  pageNumber,
  elements,
  flaggedPages,
  selectedId,
  onSelect,
  onPage,
}: Props) {
  const page = pages.find((candidate) => candidate.number === pageNumber) ?? pages[0]
  const strip = useRef<HTMLDivElement>(null)

  useEffect(() => {
    strip.current
      ?.querySelector<HTMLElement>('[aria-current="page"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' })
  }, [pageNumber])

  if (!page) return <p className="p-6 text-sm text-slate-500">No pages were rendered for this run.</p>

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      onKeyDown={(e) => {
        if ((e.target as HTMLElement).tagName === 'INPUT') return
        if (e.key === 'ArrowLeft' && pageNumber > 1) onPage(pageNumber - 1)
        if (e.key === 'ArrowRight' && pageNumber < pages.length) onPage(pageNumber + 1)
      }}
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
        <Button
          size="sm"
          variant="secondary"
          disabled={pageNumber <= 1}
          onClick={() => onPage(pageNumber - 1)}
          icon={<ChevronLeft aria-hidden className="h-4 w-4" />}
        >
          Previous
        </Button>
        <span aria-live="polite" className="text-sm font-medium text-slate-700">
          Page {pageNumber} of {pages.length}
        </span>
        <Button size="sm" variant="secondary" disabled={pageNumber >= pages.length} onClick={() => onPage(pageNumber + 1)}>
          Next <ChevronRight aria-hidden className="h-4 w-4" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-slate-100 p-4">
        <PageOverlay page={page} elements={elements} selectedId={selectedId} onSelect={onSelect} />
      </div>

      <div
        ref={strip}
        role="group"
        aria-label="Page thumbnails"
        className="flex gap-2 overflow-x-auto border-t border-slate-200 bg-white p-2"
      >
        {pages.map((item) => (
          <button
            key={item.number}
            onClick={() => onPage(item.number)}
            aria-label={`Go to page ${item.number}${flaggedPages.has(item.number) ? ' (has items to review)' : ''}`}
            aria-current={item.number === pageNumber ? 'page' : undefined}
            className={cx(
              'relative shrink-0 overflow-hidden rounded-md border-2',
              item.number === pageNumber ? 'border-brand-600' : 'border-transparent hover:border-slate-300',
            )}
          >
            <img
              src={absoluteUrl(item.image_url)}
              alt=""
              loading="lazy"
              className="block h-16 w-auto bg-white"
            />
            <span className="absolute bottom-0 left-0 rounded-tr bg-slate-900/70 px-1 text-[10px] text-white">
              {item.number}
            </span>
            {flaggedPages.has(item.number) && (
              <span aria-hidden className="absolute right-0.5 top-0.5 h-2.5 w-2.5 rounded-full bg-amber-500 ring-2 ring-white" />
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
