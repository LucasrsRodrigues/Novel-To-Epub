// Espelho leve do catalogo de estilos de capa do backend
// (backend/app/image_gen/cover_styles.py). So id + label PT — a direcao de arte
// (prompt EN) vive no backend. Manter ids e ordem identicos aos de la.

export interface CoverStyleOption {
  id: string
  label: string
}

export const COVER_STYLES: CoverStyleOption[] = [
  { id: 'art-deco-fantasy', label: 'Art Deco Fantasy' },
  { id: 'flat-graphic', label: 'Flat Graphic Illustration' },
  { id: 'cinematic-fantasy', label: 'Cinematic Fantasy' },
  { id: 'dark-fantasy', label: 'Dark Fantasy' },
  { id: 'gothic-fantasy', label: 'Gothic Fantasy' },
  { id: 'occult-esoteric', label: 'Occult / Esoteric' },
  { id: 'tarot', label: 'Tarot Inspired' },
  { id: 'editorial', label: 'Editorial Illustration' },
  { id: 'minimalist-premium', label: 'Minimalist Premium' },
  { id: 'anime-light-novel', label: 'Anime Light Novel' },
  { id: 'semi-realistic', label: 'Semi-Realistic AI Fantasy' },
  { id: 'painterly', label: 'Painterly Fantasy' },
  { id: 'cyberpunk-neon', label: 'Cyberpunk Neon' },
  { id: 'grimdark', label: 'Grimdark' },
  { id: 'mythic', label: 'Mythic Illustration' },
  { id: 'vintage-pulp', label: 'Vintage Pulp Fantasy' },
  { id: 'modern-webnovel', label: 'Modern Webnovel Cover' },
  { id: 'graphic-poster', label: 'Graphic Poster Style' },
  { id: 'cel-shading', label: 'Cel-Shading' },
  { id: 'surreal', label: 'Surreal Fantasy' },
  { id: 'high-fantasy-classic', label: 'High Fantasy Classic' },
  { id: 'noir-fantasy', label: 'Noir Fantasy' },
  { id: 'steampunk', label: 'Steampunk Fantasy' },
  { id: 'paper-cut', label: 'Paper Cut / Layered Paper' }
]

export const COVER_STYLE_LABELS: Record<string, string> = Object.fromEntries(
  COVER_STYLES.map((s) => [s.id, s.label])
)
