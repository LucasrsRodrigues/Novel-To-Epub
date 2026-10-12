export function StatTile({
  label,
  value,
  onClick
}: {
  label: string
  value: string
  onClick?: () => void
}): React.JSX.Element {
  const interactive = !!onClick
  const Tag = interactive ? 'button' : 'div'
  return (
    <Tag
      type={interactive ? 'button' : undefined}
      onClick={onClick}
      className={[
        'rounded-2xl border bg-[var(--paper-100)] px-5 py-4 text-left',
        'border-[var(--border-soft)]',
        'shadow-[0_1px_0_rgba(255,250,235,0.85)_inset,0_1px_2px_rgba(80,50,20,0.04)]',
        interactive
          ? 'cursor-pointer transition-colors hover:bg-[var(--paper-200)] hover:border-[var(--ink-300)]'
          : ''
      ].join(' ')}
    >
      <div className="font-display text-3xl font-medium tracking-tight italic text-[var(--ink-900)]">
        {value}
      </div>
      <div className="font-sans mt-1 text-[10px] tracking-[0.16em] uppercase text-[var(--ink-400)]">
        {label}
      </div>
    </Tag>
  )
}
