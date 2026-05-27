import * as React from 'react'
import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import { Check } from 'lucide-react'
import { cn } from '@renderer/lib/utils'

function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>): React.JSX.Element {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        'peer size-[18px] shrink-0 rounded-[5px] border-2',
        'border-[var(--border-medium)] bg-[var(--paper-50)]',
        'shadow-[inset_0_1px_2px_rgba(80,50,20,0.05)]',
        'transition-all outline-none',
        'data-[state=checked]:bg-[var(--stamp-red)] data-[state=checked]:border-[var(--stamp-red)] data-[state=checked]:text-[var(--paper-100)]',
        'focus-visible:ring-2 focus-visible:ring-[var(--stamp-red)]/30 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="flex items-center justify-center text-current"
      >
        <Check className="size-3" strokeWidth={3.5} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
