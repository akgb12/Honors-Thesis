import { useState } from 'react'
import { absoluteUrl } from '../api'
import { anchorToPin, bboxToRect } from '../geometry'
import { statusColor } from '../status'
import type { ReviewElement, ReviewPage } from '../types'

interface Props {
  page: ReviewPage
  elements: ReviewElement[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export default function PageOverlay({ page, elements, selectedId, onSelect }: Props) {
  const [size, setSize] = useState<{ width: number; height: number } | null>(null)
  const pageSize = { widthPt: page.width_points, heightPt: page.height_points }

  return (
    <div className="relative inline-block max-w-full border border-gray-300 bg-white">
      <img
        src={absoluteUrl(page.image_url)}
        alt={`Rendered slide page ${page.number}`}
        className="block max-w-full"
        onLoad={(e) =>
          setSize({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })
        }
      />
      {size && (
        <svg
          viewBox={`0 0 ${size.width} ${size.height}`}
          className="absolute left-0 top-0 h-full w-full"
          aria-label="Element overlay"
        >
          {elements.map((element) => {
            const color = statusColor(element.status)
            const selected = element.id === selectedId
            if (element.bbox) {
              const rect = bboxToRect(element.bbox, pageSize, size)
              return (
                <rect
                  key={element.id}
                  {...rect}
                  fill={color}
                  fillOpacity={selected ? 0.3 : 0.12}
                  stroke={color}
                  strokeWidth={selected ? 4 : 2}
                  className="cursor-pointer"
                  onClick={() => onSelect(element.id)}
                >
                  <title>{element.id}</title>
                </rect>
              )
            }
            if (element.anchor) {
              const pin = anchorToPin(element.anchor, pageSize, size)
              return (
                <circle
                  key={element.id}
                  cx={pin.x}
                  cy={pin.y}
                  r={selected ? 9 : 6}
                  fill={color}
                  stroke="white"
                  strokeWidth={2}
                  className="cursor-pointer"
                  onClick={() => onSelect(element.id)}
                >
                  <title>{element.id}</title>
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
