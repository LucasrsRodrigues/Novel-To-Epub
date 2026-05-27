import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@renderer/lib/utils'

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap font-sans font-medium',
    'transition-all duration-200',
    'disabled:pointer-events-none disabled:opacity-50',
    "[&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0",
    'outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background'
  ].join(' '),
  {
    variants: {
      variant: {
        default: [
          'rounded-xl',
          'bg-[var(--stamp-red)] text-[var(--paper-100)]',
          'shadow-[0_1px_0_rgba(255,250,235,0.25)_inset,0_2px_4px_rgba(120,40,30,0.18),0_8px_18px_-8px_rgba(120,40,30,0.40)]',
          'hover:bg-[var(--stamp-red-dark)] hover:translate-y-[-1px]',
          'active:translate-y-[0px] active:shadow-[0_1px_2px_rgba(120,40,30,0.18)]'
        ].join(' '),
        rainbow: [
          'rounded-2xl',
          'bg-rainbow text-white',
          'shadow-[0_1px_0_rgba(255,255,255,0.4)_inset,0_2px_6px_rgba(150,60,90,0.20),0_14px_28px_-10px_rgba(150,60,90,0.45)]',
          'hover:brightness-[1.07] hover:translate-y-[-1px]',
          'active:translate-y-[0px]'
        ].join(' '),
        destructive: [
          'rounded-xl',
          'bg-[var(--ink-stamp)] text-[var(--paper-100)]',
          'shadow-[0_2px_4px_rgba(120,40,30,0.20)]',
          'hover:bg-[var(--stamp-red-dark)]'
        ].join(' '),
        outline: [
          'rounded-xl',
          'border border-[var(--border-medium)] bg-[var(--paper-100)] text-[var(--ink-900)]',
          'shadow-[0_1px_0_rgba(255,250,235,0.7)_inset,0_1px_2px_rgba(80,50,20,0.06)]',
          'hover:bg-[var(--paper-200)] hover:border-[var(--ink-300)]'
        ].join(' '),
        secondary: [
          'rounded-xl',
          'bg-[var(--paper-200)] text-[var(--ink-900)]',
          'hover:bg-[var(--paper-300)]'
        ].join(' '),
        ghost: [
          'rounded-lg',
          'text-[var(--ink-500)] hover:bg-[var(--paper-200)] hover:text-[var(--ink-900)]'
        ].join(' '),
        link: 'text-[var(--stamp-red)] underline-offset-4 hover:underline'
      },
      size: {
        default: 'h-10 px-5 py-2 text-sm',
        sm: 'h-9 px-3.5 text-sm gap-1.5',
        lg: 'h-12 px-7 text-base gap-2.5 tracking-tight',
        icon: 'size-10'
      }
    },
    defaultVariants: { variant: 'default', size: 'default' }
  }
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }): React.JSX.Element {
  const Comp = asChild ? Slot : 'button'
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
