import * as React from 'react'
import * as LabelPrimitive from '@radix-ui/react-label'
import { cn } from '@renderer/lib/utils'

function Label({
  className,
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root>): React.JSX.Element {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        'font-sans inline-flex items-center gap-2 text-[13px] font-medium tracking-wide uppercase',
        'text-[var(--ink-500)]',
        'select-none peer-disabled:cursor-not-allowed peer-disabled:opacity-50',
        className
      )}
      {...props}
    />
  )
}

export { Label }
