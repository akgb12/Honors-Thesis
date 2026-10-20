import { File as FileIcon, FileCode, FileText, Image, Palette, X } from 'lucide-react'
import { fileKind, formatBytes } from '../format'
import type { ProjectFile } from '../types'

const ICONS = {
  tex: FileCode,
  pdf: FileText,
  image: Image,
  style: Palette,
  other: FileIcon,
}

export default function FileList({
  files,
  onRemove,
  disabled,
}: {
  files: ProjectFile[]
  onRemove: (path: string) => void
  disabled: boolean
}) {
  const total = files.reduce((sum, file) => sum + file.size, 0)
  const texCount = files.filter((file) => fileKind(file.path) === 'tex').length

  return (
    <details open={files.length <= 8} className="group mt-4 rounded-lg border border-slate-200">
      <summary className="flex items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-slate-50">
        <span className="font-medium text-slate-700">
          {files.length} {files.length === 1 ? 'file' : 'files'} · {formatBytes(total)}
          {texCount > 0 && <span className="font-normal text-slate-500"> · {texCount} .tex</span>}
        </span>
        <span className="text-slate-400 group-open:hidden">Show</span>
        <span className="hidden text-slate-400 group-open:inline">Hide</span>
      </summary>
      <ul className="max-h-72 divide-y divide-slate-100 overflow-auto border-t border-slate-200">
        {files.map((file) => {
          const Icon = ICONS[fileKind(file.path)]
          return (
            <li key={file.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
              <Icon aria-hidden className="h-4 w-4 shrink-0 text-slate-400" />
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-700">
                {file.path}
              </span>
              <span className="shrink-0 text-xs text-slate-400">{formatBytes(file.size)}</span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onRemove(file.path)}
                aria-label={`Remove ${file.path}`}
                className="rounded p-1 text-slate-300 hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
              >
                <X aria-hidden className="h-4 w-4" />
              </button>
            </li>
          )
        })}
      </ul>
    </details>
  )
}
