import { cn } from '@renderer/lib/utils'

/** Circular ink stamp — decorative library-checkout style seal. */
export function Stamp({
  topText = '· EX LIBRIS · PERSONAL READER ·',
  centerWord = 'Novel',
  className,
  size = 92
}: {
  topText?: string
  centerWord?: string
  className?: string
  size?: number
}): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={cn('opacity-70', className)}
      aria-hidden="true"
    >
      <defs>
        <path id="stamp-curve-top" d="M 50 50 m -38 0 a 38 38 0 1 1 76 0" />
      </defs>
      <circle cx="50" cy="50" r="46" fill="none" stroke="var(--stamp-red)" strokeWidth="1.2" />
      <circle cx="50" cy="50" r="42" fill="none" stroke="var(--stamp-red)" strokeWidth="0.6" opacity="0.7" />
      <text
        fontFamily="'Geist Variable', sans-serif"
        fontSize="6.2"
        letterSpacing="0.32em"
        fontWeight="600"
        fill="var(--stamp-red)"
      >
        <textPath href="#stamp-curve-top" startOffset="50%" textAnchor="middle">
          {topText}
        </textPath>
      </text>
      {/* decorative star/asterisk */}
      <text
        x="50"
        y="42"
        fontFamily="'Fraunces Variable', serif"
        fontSize="10"
        textAnchor="middle"
        fill="var(--stamp-red)"
      >
        ✦
      </text>
      <text
        x="50"
        y="62"
        fontFamily="'Fraunces Variable', serif"
        fontSize="14"
        fontStyle="italic"
        fontWeight="500"
        textAnchor="middle"
        fill="var(--stamp-red)"
      >
        {centerWord}
      </text>
      <text
        x="50"
        y="74"
        fontFamily="'Geist Variable', sans-serif"
        fontSize="5"
        letterSpacing="0.32em"
        fontWeight="600"
        textAnchor="middle"
        fill="var(--stamp-red)"
        opacity="0.85"
      >
        EST · 2026
      </text>
    </svg>
  )
}
