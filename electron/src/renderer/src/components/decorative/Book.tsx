import { cn } from '@renderer/lib/utils'

interface BookProps {
  color?: string
  ribbonColor?: string
  size?: number
  className?: string
  letter?: string
  showRibbon?: boolean
}

/**
 * Stylized 3D-ish book illustration with optional bookmark ribbon hanging
 * from the bottom. Used as nav icon, decorative element, etc.
 */
export function Book({
  color = 'var(--book-1)',
  ribbonColor = 'var(--bookmark-ribbon)',
  size = 56,
  className,
  letter,
  showRibbon = true
}: BookProps): React.JSX.Element {
  const aspect = 80 / 56
  return (
    <svg
      viewBox="0 0 56 80"
      width={size}
      height={Math.round(size * aspect)}
      className={cn('block shrink-0', className)}
      aria-hidden="true"
    >
      {/* drop shadow */}
      <ellipse cx="28" cy="74" rx="22" ry="2" fill="#1f1a14" opacity="0.15" />
      {/* back cover peek (gives depth) */}
      <rect x="9" y="6" width="44" height="60" rx="3" fill="#1f1a14" opacity="0.22" />
      {/* spine band */}
      <rect x="6" y="4" width="6" height="60" rx="2" fill={color} />
      <rect x="6" y="4" width="6" height="60" rx="2" fill="#000" opacity="0.20" />
      {/* main front cover */}
      <rect x="10" y="4" width="42" height="60" rx="3" fill={color} />
      {/* top page edge (cream) */}
      <rect x="11" y="4" width="40" height="2" fill="#fdf9f1" opacity="0.85" />
      {/* right page edge */}
      <rect x="50" y="6" width="2" height="58" fill="#f5ecd9" opacity="0.70" />
      {/* spine divider line */}
      <rect x="12" y="4" width="0.6" height="60" fill="#000" opacity="0.18" />
      {/* decorative title lines on cover */}
      {!letter && (
        <>
          <rect x="17" y="46" width="28" height="1.4" rx="0.7" fill="#fff" opacity="0.35" />
          <rect x="20" y="50" width="22" height="1.2" rx="0.6" fill="#fff" opacity="0.22" />
        </>
      )}
      {letter && (
        <text
          x="31"
          y="38"
          fontFamily="'Fraunces Variable', Georgia, serif"
          fontSize="22"
          fontWeight="500"
          fontStyle="italic"
          textAnchor="middle"
          fill="#fff"
          opacity="0.92"
        >
          {letter}
        </text>
      )}
      {/* bookmark ribbon hanging from the bottom */}
      {showRibbon && (
        <>
          <path d="M 24 64 H 34 V 78 L 29 73 L 24 78 Z" fill={ribbonColor} />
          <path d="M 24 64 H 34 V 66 H 24 Z" fill="#000" opacity="0.20" />
        </>
      )}
    </svg>
  )
}
