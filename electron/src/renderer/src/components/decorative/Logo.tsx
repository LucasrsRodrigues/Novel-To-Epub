import { cn } from '@renderer/lib/utils'

export function Logo({
  className,
  size = 'md'
}: {
  className?: string
  size?: 'sm' | 'md' | 'lg'
}): React.JSX.Element {
  const sizes = {
    sm: { txt: 'text-lg', arrow: 18, gap: 'gap-1.5' },
    md: { txt: 'text-2xl', arrow: 22, gap: 'gap-2' },
    lg: { txt: 'text-4xl', arrow: 32, gap: 'gap-3' }
  }
  const s = sizes[size]
  return (
    <div className={cn('font-display inline-flex items-center', s.gap, className)}>
      <span className={cn('font-medium italic tracking-tight', s.txt)} style={{ color: 'var(--ink-900)' }}>
        Novel
      </span>
      <svg
        viewBox="0 0 28 14"
        width={s.arrow}
        height={Math.round((s.arrow * 14) / 28)}
        aria-hidden="true"
      >
        <path
          d="M 2 7 H 22 M 17 2 L 22 7 L 17 12"
          stroke="var(--stamp-red)"
          strokeWidth="1.6"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className={cn('font-semibold tracking-tight', s.txt)} style={{ color: 'var(--ink-900)' }}>
        EPUB
      </span>
    </div>
  )
}
