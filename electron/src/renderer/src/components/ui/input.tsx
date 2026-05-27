import * as React from 'react'
import { cn } from '@renderer/lib/utils'

function Input({ className, type, ...props }: React.ComponentProps<'input'>): React.JSX.Element {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'font-sans flex h-10 w-full min-w-0 rounded-xl border px-4 py-2 text-sm',
        'border-[var(--border-medium)] bg-[var(--paper-50)] text-[var(--ink-900)]',
        'placeholder:text-[var(--ink-300)]',
        'shadow-[inset_0_1px_2px_rgba(80,50,20,0.06)]',
        'transition-all outline-none',
        'focus-visible:border-[var(--stamp-red)] focus-visible:bg-[var(--paper-100)] focus-visible:ring-2 focus-visible:ring-[var(--stamp-red)]/15',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'aria-invalid:border-[var(--ink-stamp)] aria-invalid:ring-2 aria-invalid:ring-[var(--ink-stamp)]/20',
        className
      )}
      {...props}
    />
  )
}

export { Input }
