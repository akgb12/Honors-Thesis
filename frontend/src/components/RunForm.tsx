import { Play } from 'lucide-react'
import { useState } from 'react'
import type { Effort } from '../types'
import { Button } from './ui'
import { cx } from './classes'

const EFFORTS: { value: Exclude<Effort, 'baseline'>; label: string; hint: string }[] = [
  { value: 'low', label: 'Low', hint: 'Quick pass with the smallest budget' },
  { value: 'medium', label: 'Medium', hint: 'Balanced; recommended' },
  { value: 'high', label: 'High', hint: 'Most repair rounds, highest budget' },
]

export default function RunForm({
  disabled,
  disabledReason,
  loading,
  onStart,
}: {
  disabled: boolean
  disabledReason: string | null
  loading: boolean
  onStart: (effort: Effort, seedWeak: string | null) => void
}) {
  const [effort, setEffort] = useState<Effort>('medium')
  const [seedWeak, setSeedWeak] = useState('')

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onStart(effort, seedWeak.trim() || null)
      }}
      className="space-y-4"
    >
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-slate-700">Effort</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {EFFORTS.map((option) => (
            <label
              key={option.value}
              className={cx(
                'cursor-pointer rounded-lg border p-3 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-600',
                effort === option.value
                  ? 'border-brand-600 bg-brand-50 ring-1 ring-brand-600'
                  : 'border-slate-200 bg-white hover:border-slate-300',
              )}
            >
              <input
                type="radio"
                name="effort"
                value={option.value}
                checked={effort === option.value}
                onChange={() => setEffort(option.value)}
                className="sr-only"
              />
              <span className="block font-semibold text-slate-900">{option.label}</span>
              <span className="block text-slate-500">{option.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <details className="text-sm">
        <summary className="font-medium text-slate-600 hover:text-slate-900">Demo options</summary>
        <label className="mt-2 block font-medium text-slate-700">
          Seed a weak description for element
          <input
            value={seedWeak}
            onChange={(e) => setSeedWeak(e.target.value)}
            placeholder="slide_04/figure_01"
            className="mt-1 block w-full max-w-sm rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm shadow-sm placeholder:text-slate-400"
          />
          <span className="mt-1 block text-xs font-normal text-slate-500">
            Forces a poor first description for this element ID so you can watch the repair loop fix it.
          </span>
        </label>
      </details>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="submit"
          variant="primary"
          loading={loading}
          disabled={disabled}
          icon={<Play aria-hidden className="h-4 w-4" />}
        >
          Start run
        </Button>
        {disabled && disabledReason && <p className="text-sm text-slate-500">{disabledReason}</p>}
      </div>
    </form>
  )
}
