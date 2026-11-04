export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md'

export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md') {
  return cx(
    'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors',
    'disabled:cursor-not-allowed disabled:opacity-50',
    size === 'sm' ? 'px-2.5 py-1.5 text-sm' : 'px-4 py-2 text-sm',
    variant === 'primary' && 'bg-brand-800 text-white shadow-sm hover:bg-brand-700',
    variant === 'secondary' &&
      'border border-slate-300 bg-white text-slate-700 shadow-sm hover:bg-slate-50',
    variant === 'ghost' && 'text-slate-600 hover:bg-slate-100',
    variant === 'danger' && 'text-red-700 hover:bg-red-50',
  )
}
