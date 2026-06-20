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

// --- Mistura ponderada de estilos ---
// O campo cover_style aceita um spec "id:peso,id:peso,..." (pesos relativos,
// normalizados pra 100% no backend). Um id sozinho = 100% (formato antigo).
// Estes helpers espelham backend/app/image_gen/cover_styles.py.

export interface StyleWeight {
  id: string
  weight: number
}

/** Parseia "id:peso,..." (ou só "id") em [{id, weight}]. Ignora ids desconhecidos. */
export function parseStyleSpec(spec: string | null | undefined): StyleWeight[] {
  if (!spec) return []
  return spec
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean)
    .map((part) => {
      const [rawId, rawW] = part.split(':')
      const id = (rawId ?? '').trim()
      const w = rawW != null ? Number(rawW.trim()) : 100
      return { id, weight: Number.isFinite(w) && w > 0 ? w : 100 }
    })
    .filter((x) => x.id && x.id in COVER_STYLE_LABELS)
}

/** Codifica [{id, weight}] em "id:peso,...". Omite pesos <= 0. */
export function encodeStyleSpec(items: StyleWeight[]): string {
  return items
    .filter((i) => i.id && i.weight > 0)
    .map((i) => `${i.id}:${Math.round(i.weight)}`)
    .join(',')
}

/** Normaliza os pesos pra % somando ~100 (pra exibir). */
export function normalizedWeights(items: StyleWeight[]): number[] {
  const total = items.reduce((a, i) => a + (i.weight > 0 ? i.weight : 0), 0)
  if (total <= 0) return items.map(() => 0)
  return items.map((i) => Math.max(1, Math.round((i.weight / total) * 100)))
}

/** Rótulo humano: "Dark Fantasy 35% · Mythic 35% · …" (ou label único, ou null). */
export function formatStyleSpec(spec: string | null | undefined): string | null {
  const items = parseStyleSpec(spec)
  if (items.length === 0) return null
  if (items.length === 1) return COVER_STYLE_LABELS[items[0].id] ?? items[0].id
  const pcts = normalizedWeights(items)
  return items.map((i, idx) => `${COVER_STYLE_LABELS[i.id] ?? i.id} ${pcts[idx]}%`).join(' · ')
}
