import { ImageOff } from 'lucide-react'
import { useState } from 'react'
import { absoluteUrl } from '../api'
import { anchorToPin, bboxToRect } from '../geometry'
import { statusStyle } from '../status'
import type { ReviewElement, ReviewPage } from '../types'

interface Props {
  page: ReviewPage
  elements: ReviewElement[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export default function PageOverlay({ page, elements, selectedId, onSelect }: Props) {
  const [size, setSize] = useState<{ width: number; height: number } | null>(null)
  const [failed, setFailed] = useState(false)
  const pageSize = { widthPt: page.width_points, heightPt: page.height_points }

  if (failed) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-500">
        <ImageOff aria-hidden className="h-6 w-6" />
        Could not load the page image.
      </div>
    )
  }

  return (
    <div className="relative mx-auto inline-block max-w-full overflow-hidden rounded-lg border border-slate-300 bg-white shadow-md">
      <img
        key={page.image_url}
        src={absoluteUrl(page.image_url)}
        alt={`Rendered slide, page ${page.number}`}
        className="block h-auto max-w-full"
        onLoad={(e) =>
          setSize({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })
        }
        onError={() => setFailed(true)}
      />
      {size && (
        <svg
          viewBox={`0 0 ${size.width} ${size.height}`}
          className="absolute left-0 top-0 h-full w-full"
          role="group"
          aria-label="Element overlay"
        >
          {elements.map((element) => {
            const style = statusStyle(element.status)
            const selected = element.id === selectedId
            const common = {
              className: 'cursor-pointer',
              onClick: () => onSelect(element.id),
            }
            if (element.bbox) {
              const rect = bboxToRect(element.bbox, pageSize, size)
              return (
                <rect
                  key={element.id}
                  {...rect}
                  {...common}
                  rx={4}
                  fill={style.color}
                  fillOpacity={selected ? 0.28 : 0.1}
                  stroke={style.color}
                  strokeWidth={selected ? 5 : 3}
                  strokeDasharray={style.dash || undefined}
                >
                  <title>
                    {element.id} · {style.label}
                  </title>
                </rect>
              )
            }
            if (element.anchor) {
              const pin = anchorToPin(element.anchor, pageSize, size)
              return (
                <circle
                  key={element.id}
                  {...common}
                  cx={pin.x}
                  cy={pin.y}
                  r={selected ? 11 : 7}
                  fill={style.color}
                  stroke="white"
                  strokeWidth={3}
                >
                  <title>
                    {element.id} · {style.label}
                  </title>
                </circle>
              )
            }
            return null
          })}
        </svg>
      )}
    </div>
  )
}
