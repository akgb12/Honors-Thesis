import { UploadCloud } from 'lucide-react'
import { useState } from 'react'
import { Spinner } from './ui'
import { cx } from './classes'

export default function Dropzone({
  onFiles,
  busy,
  compact = false,
}: {
  onFiles: (files: File[]) => void
  busy: boolean
  compact?: boolean
}) {
  const [dragging, setDragging] = useState(false)

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const files = Array.from(e.dataTransfer.files)
        if (files.length > 0 && !busy) onFiles(files)
      }}
      className={cx(
        'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed text-center transition-colors',
        'focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand-600',
        compact ? 'px-4 py-5' : 'px-6 py-9',
        dragging ? 'border-brand-500 bg-brand-50' : 'border-slate-300 bg-slate-50 hover:border-brand-400',
        busy && 'pointer-events-none opacity-70',
      )}
    >
      {busy ? (
        <Spinner className="mb-2 h-6 w-6 text-brand-700" />
      ) : (
        <UploadCloud aria-hidden className="mb-2 h-7 w-7 text-brand-700" />
      )}
      <span className="text-sm font-medium text-slate-800">
        {busy ? 'Uploading…' : 'Drop your project .zip or files here'}
      </span>
      <span className="mt-0.5 text-sm text-slate-500">
        or <span className="font-medium text-brand-700 underline">browse your computer</span>
      </span>
      <input
        type="file"
        multiple
        disabled={busy}
        className="sr-only"
        aria-label="Upload a project zip or individual files"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          if (files.length > 0) onFiles(files)
          e.target.value = ''
        }}
      />
    </label>
  )
}
