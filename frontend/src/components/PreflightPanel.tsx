import { CircleCheck, FileUp } from 'lucide-react'
import { useId } from 'react'
import type { Preflight } from '../types'
import { Alert, Badge, Skeleton } from './ui'

interface Props {
  preflight: Preflight | null
  checking: boolean
  busy: boolean
  mainFile: string | null
  onSelectMain: (file: string) => void
  onFill: (path: string, file: File) => void
}

export default function PreflightPanel({
  preflight,
  checking,
  busy,
  mainFile,
  onSelectMain,
  onFill,
}: Props) {
  const selectId = useId()

  if (!preflight) {
    return checking ? <Skeleton className="h-16" /> : null
  }

  const candidates = preflight.main_candidates
  const problem = preflight.problem

  return (
    <div className="space-y-4" aria-busy={checking}>
      {problem && problem.code !== 'choose_main_file' && (
        <Alert
          tone="warning"
          title={problem.code === 'no_tex_files' ? 'No LaTeX source found' : 'No Beamer slides found'}
        >
          {problem.message}
        </Alert>
      )}

      {candidates.length > 1 && (
        <div>
          {problem?.code === 'choose_main_file' && (
            <div className="mb-3">
              <Alert tone="info" title="Choose a main file">
                {problem.message}
              </Alert>
            </div>
          )}
          <label htmlFor={selectId} className="block text-sm font-medium text-slate-700">
            Main Beamer file
          </label>
          <select
            id={selectId}
            value={mainFile ?? ''}
            onChange={(e) => e.target.value && onSelectMain(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm"
          >
            <option value="" disabled>
              Select a file… ({candidates.length} found)
            </option>
            {candidates.map((candidate) => (
              <option key={candidate} value={candidate}>
                {candidate}
              </option>
            ))}
          </select>
        </div>
      )}

      {preflight.main_file && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-500">Main file</span>
          <Badge tone="brand" className="font-mono">
            {preflight.main_file}
          </Badge>
          {preflight.ok && (
            <Badge tone="success">
              <CircleCheck aria-hidden className="h-3.5 w-3.5" /> Ready to run
            </Badge>
          )}
        </div>
      )}

      {preflight.critical_blockers.length > 0 && (
        <Alert tone="danger" title="These problems must be fixed first">
          <ul className="list-disc pl-5">
            {preflight.critical_blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </Alert>
      )}

      {preflight.missing_images.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium text-slate-800">
            {preflight.missing_images.length} image{preflight.missing_images.length === 1 ? ' is' : 's are'}{' '}
            missing. Upload a file for each slot:
          </p>
          <ul className="space-y-2">
            {preflight.missing_images.map((slot) => (
              <li
                key={slot}
                className="flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2"
              >
                <code className="min-w-0 truncate text-xs text-amber-900">{slot}</code>
                <label className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-amber-300 bg-white px-2.5 py-1 text-sm font-medium text-amber-900 hover:bg-amber-100 has-[:disabled]:opacity-50">
                  <FileUp aria-hidden className="h-4 w-4" />
                  Upload
                  <input
                    type="file"
                    disabled={busy}
                    className="sr-only"
                    aria-label={`Upload file for ${slot}`}
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) onFill(slot, file)
                      e.target.value = ''
                    }}
                  />
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}

      {preflight.issues.length > 0 && (
        <details className="rounded-lg border border-slate-200 text-sm">
          <summary className="px-3 py-2 font-medium text-slate-700 hover:bg-slate-50">
            {preflight.issues.length} pre-flight note{preflight.issues.length === 1 ? '' : 's'}
          </summary>
          <ul className="max-h-60 divide-y divide-slate-100 overflow-auto border-t border-slate-200">
            {preflight.issues.map((issue, index) => (
              <li key={`${issue.code}-${index}`} className="flex gap-2 px-3 py-2">
                <Badge tone={issue.severity === 'error' ? 'danger' : 'warning'}>{issue.severity}</Badge>
                <span className="min-w-0 text-slate-700">
                  {issue.message}
                  {issue.source_file && (
                    <span className="block font-mono text-xs text-slate-400">
                      {issue.source_file}
                      {issue.line ? `:${issue.line}` : ''}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
