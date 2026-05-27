import { cn } from '@renderer/lib/utils'

/** Small italic serif "folio" number — like a printed page number. */
export function Folio({
  n,
  className
}: {
  n: number | string
  className?: string
}): React.JSX.Element {
  const str = typeof n === 'number' ? String(n).padStart(3, '0') : n
  return <span className={cn('folio text-[0.7rem]', className)}>— {str} —</span>
}
