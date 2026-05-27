import * as React from 'react'
import { cn } from '@renderer/lib/utils'

function Card({ className, ...props }: React.ComponentProps<'div'>): React.JSX.Element {
  return (
    <div
      data-slot="card"
      className={cn(
        'relative flex flex-col gap-5 rounded-2xl border px-6 py-6 text-[var(--ink-900)]',
        'border-[var(--border-soft)] bg-[var(--paper-100)]',
        'shadow-[0_1px_0_rgba(255,250,235,0.85)_inset,0_2px_3px_rgba(80,50,20,0.04),0_18px_36px_-22px_rgba(80,50,20,0.22)]',
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<'div'>): React.JSX.Element {
  return <div data-slot="card-header" className={cn('grid gap-1.5', className)} {...props} />
}

function CardTitle({ className, ...props }: React.ComponentProps<'div'>): React.JSX.Element {
  return (
    <div
      data-slot="card-title"
      className={cn(
        'font-display text-xl font-medium tracking-tight text-[var(--ink-900)]',
        className
      )}
      {...props}
    />
  )
}

function CardDescription({
  className,
  ...props
}: React.ComponentProps<'div'>): React.JSX.Element {
  return (
    <div
      data-slot="card-description"
      className={cn('font-sans text-sm leading-relaxed text-[var(--ink-500)]', className)}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<'div'>): React.JSX.Element {
  return <div data-slot="card-content" className={cn('', className)} {...props} />
}

function CardFooter({ className, ...props }: React.ComponentProps<'div'>): React.JSX.Element {
  return (
    <div data-slot="card-footer" className={cn('flex items-center', className)} {...props} />
  )
}

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent }
