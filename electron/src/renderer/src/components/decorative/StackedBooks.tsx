import { cn } from '@renderer/lib/utils'

/** Hero illustration: stacked colorful books with one standing on top. */
export function StackedBooks({ className }: { className?: string }): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 300 220"
      width="300"
      height="220"
      className={cn('block', className)}
      aria-hidden="true"
    >
      {/* ground shadow */}
      <ellipse cx="150" cy="208" rx="118" ry="6" fill="#1f1a14" opacity="0.10" />

      {/* book 1: teal, bottom */}
      <g transform="translate(22 170) rotate(-2.5 130 18)">
        <rect width="256" height="34" rx="4" fill="#3a6063" />
        <rect width="256" height="3" fill="#fdf9f1" />
        <rect y="3" width="256" height="1" fill="#000" opacity="0.18" />
        <rect x="234" y="6" width="3" height="25" fill="#000" opacity="0.18" />
        <rect x="36" y="14" width="92" height="2" fill="#fff" opacity="0.40" />
        <rect x="36" y="19" width="64" height="1.5" fill="#fff" opacity="0.25" />
      </g>

      {/* book 2: terracotta */}
      <g transform="translate(14 134) rotate(2 130 18)">
        <rect width="270" height="32" rx="4" fill="#b85b3f" />
        <rect width="270" height="3" fill="#fdf9f1" />
        <rect y="3" width="270" height="1" fill="#000" opacity="0.18" />
        <rect x="32" y="12" width="120" height="2" fill="#fff" opacity="0.42" />
        <rect x="32" y="17" width="60" height="1.5" fill="#fff" opacity="0.22" />
      </g>

      {/* book 3: mustard, with ribbon hanging out the side */}
      <g transform="translate(30 100) rotate(-1.8 115 16)">
        <rect width="234" height="30" rx="4" fill="#b58932" />
        <rect width="234" height="3" fill="#fdf9f1" />
        <rect y="3" width="234" height="1" fill="#000" opacity="0.16" />
        <rect x="40" y="11" width="80" height="1.6" fill="#fff" opacity="0.4" />
        {/* tiny bookmark ribbon poking out the right side */}
        <path d="M 230 8 H 244 V 24 L 237 19 L 230 24 Z" fill="var(--bookmark-ribbon)" />
        <path d="M 230 8 H 244 V 10 H 230 Z" fill="#000" opacity="0.20" />
      </g>

      {/* book 4: plum, narrower top */}
      <g transform="translate(46 72) rotate(3 90 14)">
        <rect width="186" height="26" rx="4" fill="#715079" />
        <rect width="186" height="3" fill="#fdf9f1" />
        <rect x="26" y="10" width="80" height="1.5" fill="#fff" opacity="0.36" />
      </g>

      {/* protagonist: standing book on top — sage, with ribbon */}
      <g transform="translate(118 4)">
        <ellipse cx="26" cy="76" rx="22" ry="1.5" fill="#1f1a14" opacity="0.20" />
        {/* back cover peek */}
        <rect x="3" y="6" width="48" height="64" rx="3" fill="#1f1a14" opacity="0.22" />
        {/* spine */}
        <rect x="0" y="4" width="6" height="64" rx="2" fill="#5b8068" />
        <rect x="0" y="4" width="6" height="64" rx="2" fill="#000" opacity="0.22" />
        {/* cover */}
        <rect x="4" y="4" width="46" height="64" rx="3" fill="#5b8068" />
        <rect x="5" y="4" width="44" height="2" fill="#fdf9f1" opacity="0.85" />
        <rect x="48" y="6" width="2" height="62" fill="#f5ecd9" opacity="0.7" />
        {/* monogram */}
        <text
          x="27"
          y="36"
          fontFamily="'Fraunces Variable', Georgia, serif"
          fontSize="22"
          fontWeight="500"
          fontStyle="italic"
          textAnchor="middle"
          fill="#fff"
          opacity="0.92"
        >
          N
        </text>
        <rect x="10" y="50" width="34" height="1.2" rx="0.6" fill="#fff" opacity="0.35" />
        <rect x="14" y="54" width="26" height="1" rx="0.5" fill="#fff" opacity="0.22" />
        {/* bookmark ribbon hanging */}
        <path d="M 18 68 H 32 V 80 L 25 75 L 18 80 Z" fill="var(--bookmark-ribbon)" />
        <path d="M 18 68 H 32 V 70 H 18 Z" fill="#000" opacity="0.20" />
      </g>
    </svg>
  )
}
