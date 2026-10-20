import { statusStyle } from '../status'

// A small line sample showing a status color and dash pattern
export default function StatusSwatch({ status, size = 22 }: { status: string; size?: number }) {
  const style = statusStyle(status)
  return (
    <svg aria-hidden width={size} height="10" viewBox={`0 0 ${size} 10`} className="shrink-0">
      <line
        x1="1"
        y1="5"
        x2={size - 1}
        y2="5"
        stroke={style.color}
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={style.dash || undefined}
      />
    </svg>
  )
}
