import type { Preflight } from '../types'

interface Props {
  preflight: Preflight | null
  busy: boolean
  onFill: (path: string, file: File) => void
  onRecheck: () => void
}

export default function PreflightPanel({ preflight, busy, onFill, onRecheck }: Props) {
  return (
    <section className="space-y-2 rounded border border-gray-200 bg-white p-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Pre-flight</h2>
        <button onClick={onRecheck} className="text-sm text-blue-700 hover:underline">
          Re-check
        </button>
      </div>
      {!preflight && <p className="text-sm text-gray-500">No pre-flight result yet.</p>}
      {preflight && (
        <>
          <p className="text-sm">
            Main file: <code>{preflight.main_file}</code> ·{' '}
            <span className={preflight.ok ? 'text-green-700' : 'text-red-700'}>
              {preflight.ok ? 'ready to run' : 'not ready'}
            </span>
          </p>
          {preflight.critical_blockers.length > 0 && (
            <ul className="list-disc pl-5 text-sm text-red-700">
              {preflight.critical_blockers.map((blocker) => (
                <li key={blocker}>Blocker: {blocker}</li>
              ))}
            </ul>
          )}
          {preflight.missing_images.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Missing files, upload one for each slot:</p>
              {preflight.missing_images.map((slot) => (
                <label key={slot} className="block text-sm">
                  <code>{slot}</code>
                  <input
                    type="file"
                    disabled={busy}
                    aria-label={`Upload ${slot}`}
                    className="ml-2"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) onFill(slot, file)
                    }}
                  />
                </label>
              ))}
            </div>
          )}
          {preflight.issues.length > 0 && (
            <ul className="text-sm text-gray-700">
              {preflight.issues.map((issue, index) => (
                <li key={`${issue.code}-${index}`}>
                  <span className="font-medium">{issue.severity}</span>: {issue.message}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
