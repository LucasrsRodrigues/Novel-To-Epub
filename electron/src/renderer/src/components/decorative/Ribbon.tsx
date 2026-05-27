import { cn } from '@renderer/lib/utils'

/**
 * Standalone bookmark ribbon — overlay on novel covers in Library.
 * Hangs from the top of an element (use absolute positioning).
 */
export function Ribbon({
  color = 'var(--bookmark-ribbon)',
  width = 18,
  height = 34,
  className
}: {
  color?: string
  width?: number
  height?: number
  className?: string
}): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 18 34"
      width={width}
      height={height}
      className={cn('drop-shadow-[0_2px_2px_rgba(60,40,20,0.25)]', className)}
      aria-hidden="true"
    >
      <path d="M 0 0 H 18 V 34 L 9 27 L 0 34 Z" fill={color} />
      {/* fold shadow */}
      <path d="M 0 0 H 18 V 3 H 0 Z" fill="#000" opacity="0.18" />
    </svg>
  )
}
