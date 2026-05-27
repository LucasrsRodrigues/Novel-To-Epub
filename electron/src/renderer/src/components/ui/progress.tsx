import * as React from 'react'
import * as ProgressPrimitive from '@radix-ui/react-progress'
import { cn } from '@renderer/lib/utils'

interface ProgressProps extends React.ComponentProps<typeof ProgressPrimitive.Root> {
  /** Use the rainbow gradient (for primary actions) instead of stamp red. */
  rainbow?: boolean
}

function Progress({ className, value, rainbow, ...props }: ProgressProps): React.JSX.Element {
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      className={cn(
        'relative h-2.5 w-full overflow-hidden rounded-full',
        'bg-[var(--paper-300)] shadow-[inset_0_1px_2px_rgba(80,50,20,0.10)]',
        className
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className={cn(
          'h-full w-full flex-1 transition-all duration-300 rounded-full',
          rainbow ? 'bg-rainbow' : 'bg-[var(--stamp-red)]'
        )}
        style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
