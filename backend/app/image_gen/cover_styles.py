"""Catalogo de estilos de arte pra capa por IA.

Cada estilo tem um `id` (slug estavel, usado no DB/API), um `label` em PT-BR (pra
UI) e um `prompt` em ingles — uma direcao de arte concisa injetada no prompt de
geracao da imagem (Gemini Flash Image). O id e a chave de tudo: a UI manda o id,
o backend resolve o prompt aqui. Ids desconhecidos caem em "automatico" (None).

A ORDEM aqui e a ordem mostrada na UI. O espelho id+label vive em
`electron/src/renderer/src/lib/coverStyles.ts` — manter os ids identicos.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoverStyle:
    id: str
    label: str
    prompt: str


# Ordem = ordem de exibicao na UI.
COVER_STYLES: tuple[CoverStyle, ...] = (
    CoverStyle(
        "art-deco-fantasy", "Art Deco Fantasy",
        "Art Deco fantasy aesthetic: elegant geometric shapes, gold ornamental "
        "filigree, strict symmetrical composition, luxurious refined look, mystic "
        "symbols, long sleek lines, sophisticated 1920s–30s palette.",
    ),
    CoverStyle(
        "flat-graphic", "Flat Graphic Illustration",
        "Flat graphic vector illustration: minimal shading, bold flat color fields, "
        "clean vector shapes, strong silhouettes, little realistic texture, "
        "shape-driven composition.",
    ),
    CoverStyle(
        "cinematic-fantasy", "Cinematic Fantasy",
        "Cinematic fantasy: epic widescreen composition, a small figure dwarfed by a "
        "vast environment, dramatic lighting, heavy atmosphere, movie-poster feel, "
        "deep cinematic depth, strong narrative focus.",
    ),
    CoverStyle(
        "dark-fantasy", "Dark Fantasy",
        "Dark fantasy: deep shadowed tones, mist and smoke, oppressive atmosphere, "
        "gothic architecture, strong contrast, dark magic, melancholic mood.",
    ),
    CoverStyle(
        "gothic-fantasy", "Gothic Fantasy",
        "Gothic fantasy: cathedrals and churches, ornamental detail, Victorian vibe, "
        "black-red-gold palette, religious symbolism, ancient atmosphere, elegant horror.",
    ),
    CoverStyle(
        "occult-esoteric", "Occult / Esoteric",
        "Occult esoteric aesthetic: arcane symbols, ritual geometry, eyes, runes and "
        "circles, tarot and alchemy motifs, mysterious mood, symbolic composition.",
    ),
    CoverStyle(
        "tarot", "Tarot Inspired",
        "Tarot-card aesthetic: decorative ornate border frame, centered symmetrical "
        "composition, symbolic figures, sacred geometry, mystical ritualistic look, "
        "vertical reading.",
    ),
    CoverStyle(
        "editorial", "Editorial Illustration",
        "Editorial illustration: graphic-design-driven, visual simplification, strong "
        "visual narrative, clever composition, premium magazine/book look.",
    ),
    CoverStyle(
        "minimalist-premium", "Minimalist Premium",
        "Minimalist premium design: very few elements, generous negative space, bold "
        "iconic focal motif, reduced palette, refined elegance, strong identity.",
    ),
    CoverStyle(
        "anime-light-novel", "Anime Light Novel",
        "Anime light-novel cover: a central character with expressive eyes and detailed "
        "hair, glowing magical effects, stylized background, vibrant colors, heroic pose.",
    ),
    CoverStyle(
        "semi-realistic", "Semi-Realistic AI Fantasy",
        "Semi-realistic fantasy render: highly detailed face, intense lighting, magical "
        "glow, detailed armor, polished game-poster look, hyper-rendered finish.",
    ),
    CoverStyle(
        "painterly", "Painterly Fantasy",
        "Painterly fantasy: visible brushstrokes, painting texture, artistic lighting, "
        "traditional concept-art feel, organic color blending.",
    ),
    CoverStyle(
        "cyberpunk-neon", "Cyberpunk Neon",
        "Cyberpunk neon: blue and pink neon, futuristic rainy city, glowing lights and "
        "holograms, high contrast, urban high-tech atmosphere.",
    ),
    CoverStyle(
        "grimdark", "Grimdark",
        "Grimdark fantasy: implied violence, a decaying world, desaturated palette, "
        "brutal visuals, hopeless despairing mood, adult tone.",
    ),
    CoverStyle(
        "mythic", "Mythic Illustration",
        "Mythic illustration: legendary near-divine figures, symbolic composition, "
        "celestial elements, epic scale, ancient timeless feel.",
    ),
    CoverStyle(
        "vintage-pulp", "Vintage Pulp Fantasy",
        "Vintage pulp fantasy: bold saturated colors, exaggerated dynamic poses, "
        "classic adventure, retro 70s–80s aesthetic.",
    ),
    CoverStyle(
        "modern-webnovel", "Modern Webnovel Cover",
        "Modern webnovel cover: a dominant protagonist, energetic background, particles "
        "and glow, exaggerated contrast, focus on cool-factor, reads well as a thumbnail.",
    ),
    CoverStyle(
        "graphic-poster", "Graphic Poster Style",
        "Graphic poster style: layered composition, poster look, strong silhouettes, "
        "visual storytelling, modern aesthetic.",
    ),
    CoverStyle(
        "cel-shading", "Cel-Shading",
        "Cel-shaded render: hard cell shadows, anime/game look, bold outlines, solid "
        "colors, stylized rendering.",
    ),
    CoverStyle(
        "surreal", "Surreal Fantasy",
        "Surreal fantasy: impossible elements, visual distortion, abstract symbols, "
        "dreamlike atmosphere, conceptual composition, focus on strangeness.",
    ),
    CoverStyle(
        "high-fantasy-classic", "High Fantasy Classic",
        "Classic high fantasy: castles, dragons and mages, vast landscapes, adventurous "
        "feel, epic lighting, traditional fantasy art.",
    ),
    CoverStyle(
        "noir-fantasy", "Noir Fantasy",
        "Noir fantasy: dominant black-and-white, dramatic chiaroscuro lighting, urban "
        "mystery, detective/occult theme, smoke and shadows, investigative mood.",
    ),
    CoverStyle(
        "steampunk", "Steampunk Fantasy",
        "Steampunk fantasy: gears and cogs, copper and bronze, antique technology, "
        "Victorian aesthetic, mechanical machines, airships and clockwork.",
    ),
    CoverStyle(
        "paper-cut", "Paper Cut / Layered Paper",
        "Layered paper-cut style: cut-paper look, layered depth, soft edges, handcrafted "
        "feel, simple shapes, theatrical diorama composition.",
    ),
)

_BY_ID: dict[str, CoverStyle] = {s.id: s for s in COVER_STYLES}


# ---------------------------------------------------------------------------
# Mistura ponderada de estilos
#
# O campo `cover_style` aceita um SPEC: "id:peso,id:peso,..." (pesos relativos,
# normalizados pra 100%). Um id sozinho (sem ":") = 100% daquele estilo — formato
# antigo continua valendo (retrocompativel). Ex de mistura:
#   "dark-fantasy:35,mythic:35,occult-esoteric:20,noir-fantasy:10"
#
# O modelo de imagem nao faz matematica literal de %, entao traduzimos o peso em
# linguagem de DOMINANCIA (dominant/major/secondary/accent) — e o que entrega a
# sensacao de "70% disso, 20% daquilo".
# ---------------------------------------------------------------------------

def parse_style_spec(spec: str | None) -> list[tuple[CoverStyle, int]]:
    """Parseia o spec em [(CoverStyle, peso_em_%)], ordenado por peso desc.

    - Pesos relativos -> normalizados pra somar ~100.
    - Ids sem ":peso" recebem peso 1 (divisao igual se ninguem especificar peso).
    - Ids desconhecidos / pesos <= 0 sao ignorados. Spec vazio -> [].
    """
    if not spec:
        return []
    raw: list[tuple[CoverStyle, float]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        sid, sep, w = part.partition(":")
        sid = sid.strip()
        weight = 1.0
        if sep:
            try:
                weight = float(w.strip())
            except ValueError:
                weight = 1.0
        style = _BY_ID.get(sid)
        if style is None or weight <= 0:
            continue
        raw.append((style, weight))
    if not raw:
        return []
    total = sum(w for _, w in raw)
    norm = [(s, max(1, round(w / total * 100))) for s, w in raw]
    norm.sort(key=lambda x: x[1], reverse=True)
    return norm


_ROLE_HINTS = {
    "DOMINANT": "defines the overall palette, medium and mood of the whole image",
    "MAJOR": "strongly present throughout the composition",
    "SECONDARY": "clearly present as recurring motifs and texture",
    "ACCENT": "subtle finishing touches only",
}


def _role_for(pct: int) -> str:
    if pct >= 50:
        return "DOMINANT"
    if pct >= 25:
        return "MAJOR"
    if pct >= 12:
        return "SECONDARY"
    return "ACCENT"


def style_prompt(style_id: str | None) -> str | None:
    """Resolve a direcao de arte pra um id OU spec ponderado.

    - None/desconhecido/vazio -> None (IA decide, comportamento padrao).
    - 1 estilo -> o prompt cru daquele estilo (igual antes).
    - 2+ estilos -> bloco de BLEND ponderado (dominancia por linguagem).
    """
    parsed = parse_style_spec(style_id)
    if not parsed:
        return None
    if len(parsed) == 1:
        return parsed[0][0].prompt
    lines = []
    for style, pct in parsed:
        role = _role_for(pct)
        lines.append(f"- {role} (~{pct}%, {_ROLE_HINTS[role]}): {style.prompt}")
    body = "\n".join(lines)
    return (
        "a deliberate weighted blend of multiple aesthetics, fused into ONE "
        "cohesive art direction (NOT a collage):\n"
        f"{body}\n"
        "The dominant aesthetic governs the whole image (palette, medium, mood); "
        "the lower-weighted aesthetics layer in as motifs and accents without "
        "breaking the unified look."
    )


def style_label(style_id: str | None) -> str | None:
    """Label humano pra UI/logs. Mistura -> 'Dark Fantasy 35% · Mythic 35% · …'."""
    parsed = parse_style_spec(style_id)
    if not parsed:
        return None
    if len(parsed) == 1:
        return parsed[0][0].label
    return " · ".join(f"{s.label} {pct}%" for s, pct in parsed)
