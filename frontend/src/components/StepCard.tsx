import { Check } from 'lucide-react'
import type { ReactNode } from 'react'
import { cx } from './classes'

export default function StepCard({
  number,
  title,
  description,
  done,
  action,
  children,
}: {
  number: number
  title: string
  description?: string
  done?: boolean
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="flex items-start gap-3 px-5 pt-4">
        <span
          aria-hidden
          className={cx(
            'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
            done ? 'bg-emerald-600 text-white' : 'bg-brand-800 text-white',
          )}
        >
          {done ? <Check className="h-4 w-4" /> : number}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-slate-900">
            <span className="sr-only">Step {number}: </span>
            {title}
            {done && <span className="sr-only"> (complete)</span>}
          </h2>
          {description && <p className="text-sm text-slate-500">{description}</p>}
        </div>
        {action}
      </header>
      <div className="px-5 pb-5 pt-4">{children}</div>
    </section>
  )
}
