"""Geracao de capas custom com Gemini Flash Image.

Pipeline:
  1. ``build_brief()`` — chamada de TEXTO (Gemini Flash) com amostras de capitulos
     + glossario + descricao da novel → 2 frases visuais concretas (scene + style)
  2. ``generate_image()`` — chamada de IMAGEM (Gemini Flash Image) com prompt
     construido a partir do brief
  3. Tudo cacheado em ``generated_covers`` por (novel_id, volume_title)

A capa SUBSTITUI a raspada do site quando ``ai_cover=True`` no orchestrator.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from app.db.cache import ChapterCache
from app.db.cover_cache import CoverCache
from app.image_gen.cover_styles import style_prompt
from app.db.settings_store import SettingsStore
from app.db.usage_store import UsageStore
from app.logging_conf import get_logger
from app.models import ChapterContent, NovelMeta
from app.translation.glossary import GlossaryEntry
from app.translation.retry import call_with_retry

log = get_logger("cover")


# Fontes do sistema mac (Georgia tem 4 variantes — perfeito pra capa editorial).
# Em outra plataforma, Pillow vai cair no default bitmap (feio) — TODO embarcar
# uma TTF em backend/app/assets/ pra cross-platform.
_FONT_REGULAR = "/System/Library/Fonts/Supplemental/Georgia.ttf"
_FONT_BOLD = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
_FONT_ITALIC = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"
_FONT_BOLD_ITALIC = "/System/Library/Fonts/Supplemental/Georgia Bold Italic.ttf"


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        log.warning("font_missing", path=path)
        return ImageFont.load_default()


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: float,
    draw: ImageDraw.ImageDraw,
    max_lines: int = 3,
) -> list[str]:
    """Quebra texto em ate `max_lines` linhas pra caber em `max_width` px."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        bb = draw.textbbox((0, 0), candidate, font=font)
        if (bb[2] - bb[0]) <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    if len(lines) > max_lines:
        # Trunca a ultima linha visivel + ellipsis
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]
        lines[-1] = lines[-1][:60].rstrip() + "…"
    return lines


def _composite_title_overlay(
    image_bytes: bytes,
    *,
    novel_title: str,
    volume_title: str | None,
    mime: str = "image/png",
) -> tuple[bytes, str]:
    """Sobrepoe nome da novel (top da faixa) + titulo do volume (bottom).

    Layout (terco inferior da capa):
      [faixa com gradient escuro]
        NOME DA NOVEL (caps, tracking)
        ───── (linha vermelha curta)
        Volume Title (bold italic, quebra em ate 3 linhas)
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    W, H = img.size

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Faixa inferior com gradient (transparente -> escuro tirando preto). Altura
    # generosa pra deixar respiro pro titulo do volume quando quebra em 2-3 linhas.
    band_h = int(H * 0.32)
    band_top = H - band_h
    for y in range(band_h):
        # curva mais "amassada" no comeco do gradient pra parecer cinematica
        t = (y / band_h) ** 1.4
        alpha = int(225 * t)
        draw.line([(0, band_top + y), (W, band_top + y)], fill=(12, 8, 5, alpha))

    # --- Tipografia ---
    # Tamanhos calibrados pra que o conjunto (novel name + sep + ate 3 linhas
    # de volume title) caiba sempre na banda, com folga inferior.
    novel_font_size = max(14, int(H * 0.026))
    volume_font_size = max(20, int(H * 0.046))
    novel_font = _load_font(_FONT_REGULAR, novel_font_size)
    volume_font = _load_font(_FONT_BOLD_ITALIC, volume_font_size)

    # Novel name (perto do topo da faixa): uppercase + tracking via espaco
    novel_text = " ".join(novel_title.upper())  # tracking visual
    nb = draw.textbbox((0, 0), novel_text, font=novel_font)
    novel_w = nb[2] - nb[0]
    if novel_w > W * 0.88:  # fallback sem tracking se nome longo
        novel_text = novel_title.upper()
        nb = draw.textbbox((0, 0), novel_text, font=novel_font)
        novel_w = nb[2] - nb[0]
    novel_y = band_top + int(band_h * 0.18)
    draw.text(
        ((W - novel_w) // 2, novel_y),
        novel_text,
        font=novel_font,
        fill=(245, 232, 205, 240),
    )

    # Linha vermelha fina separadora — entre nome da novel e titulo do volume
    sep_y = novel_y + novel_font_size + int(band_h * 0.06)
    sep_w_half = int(W * 0.14)
    sep_thickness = max(2, int(H * 0.0014))
    draw.line(
        [(W // 2 - sep_w_half, sep_y), (W // 2 + sep_w_half, sep_y)],
        fill=(170, 55, 42, 230),
        width=sep_thickness,
    )

    # Volume title (multi-linha, centrado): ate 3 linhas com line-height apertado
    if volume_title:
        lines = _wrap_text(volume_title, volume_font, W * 0.86, draw, max_lines=3)
        y_cursor = sep_y + int(band_h * 0.08)
        line_height = int(volume_font_size * 1.10)
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=volume_font)
            lw = lb[2] - lb[0]
            draw.text(
                ((W - lw) // 2, y_cursor),
                line,
                font=volume_font,
                fill=(255, 250, 240, 255),
            )
            y_cursor += line_height

    final = Image.alpha_composite(img, overlay).convert("RGB")
    out = BytesIO()
    if mime == "image/png":
        final.save(out, "PNG", optimize=True)
        return out.getvalue(), "image/png"
    final.save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue(), "image/jpeg"


class CoverGenError(RuntimeError):
    pass


def _resolve_api_key() -> str:
    cfg = SettingsStore().get()
    key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or cfg.get("gemini_api_key")
    )
    if not key:
        raise CoverGenError(
            "GEMINI_API_KEY ausente. Configure em /api/settings ou no env."
        )
    return key


@dataclass
class _Excerpt:
    index: int
    text: str


def _sample_chapters(chapters: list[ChapterContent], max_chars: int = 1400) -> list[_Excerpt]:
    """Pega 1, 2 ou 3 capitulos (primeiro/meio/ultimo) e devolve o texto puro."""
    if not chapters:
        return []
    if len(chapters) == 1:
        idxs = [0]
    elif len(chapters) == 2:
        idxs = [0, 1]
    else:
        idxs = [0, len(chapters) // 2, len(chapters) - 1]
    out: list[_Excerpt] = []
    for i in idxs:
        ch = chapters[i]
        text = re.sub(r"<[^>]+>", " ", ch.html)
        text = re.sub(r"\s+", " ", text).strip()
        out.append(_Excerpt(index=ch.index, text=text[:max_chars]))
    return out


def _glossary_summary(glossary: list[GlossaryEntry], limit: int = 12) -> str:
    if not glossary:
        return "(vazio)"
    chars = [e for e in glossary if e.kind == "character"][: limit // 2 + 1]
    things = [
        e
        for e in glossary
        if e.kind in ("place", "ability", "organization", "system_term")
    ][: limit // 2]
    lines = []
    for e in chars + things:
        bits = [e.term]
        if e.gender not in ("n/a", "unknown"):
            bits.append(e.gender)
        bits.append(f"({e.kind})")
        if e.notes:
            bits.append(e.notes[:80])
        lines.append("- " + " · ".join(bits))
    return "\n".join(lines)


class _Brief(BaseModel):
    scene: str = Field(
        description=(
            "Descricao visual concreta de UMA cena emblematica (objetos, "
            "personagens, ambiente, atmosfera). 1-2 frases. Sem metaforas."
        )
    )
    style: str = Field(
        description=(
            "Direcao estetica: paleta, iluminacao, estilo de ilustracao "
            "(ex: dark fantasy oil painting, neo-noir watercolor). 1 frase."
        )
    )


_BRIEF_SYSTEM = """\
Voce e um diretor de arte que cria briefs visuais para capas de livros de web novel.

Receba: descricao da obra + lista de personagens/conceitos do glossario + 3
excertos de capitulos (inicio, meio, fim do volume).

Saida: um JSON com:
  - "scene": cena visual concreta para a capa (1-2 frases). Pessoas, objetos,
    ambiente, atmosfera. Evite resumos de enredo — pense VISUAL.
  - "style": direcao estetica (paleta, iluminacao, referencia de tecnica).

A cena deve refletir o tom da OBRA (use os termos do glossario) E o arco dos
capitulos amostrados. Pense num poster, nao num spoiler.
"""


def _build_brief_user_prompt(
    novel_meta: NovelMeta,
    volume_title: str | None,
    excerpts: list[_Excerpt],
    glossary: list[GlossaryEntry],
    style_hint: str | None = None,
) -> str:
    excerpts_block = "\n\n".join(
        f"=== Capitulo {e.index} ===\n{e.text}" for e in excerpts
    )
    # Quando o usuario escolheu um estilo de arte fixo, a `style` do brief sera
    # ignorada (o prompt de imagem usa o estilo escolhido). Mas ainda avisamos o
    # modelo pra que a CENA combine com a estetica alvo.
    style_block = (
        f"\nESTILO DE ARTE ALVO (a cena deve combinar com esta estetica):\n{style_hint}\n"
        if style_hint
        else ""
    )
    return f"""NOVEL: {novel_meta.title}
VOLUME: {volume_title or '(volume sem titulo definido)'}
DESCRICAO DA NOVEL:
{novel_meta.description or '(sem descricao)'}

GLOSSARIO (personagens / conceitos / termos chave):
{_glossary_summary(glossary)}

EXCERTOS DOS CAPITULOS COBERTOS:
{excerpts_block}
{style_block}
Produza o JSON com `scene` + `style`."""


_SERIES_BLOCK_HEADER = "SERIES CONSISTENCY"


def _series_consistency_block(series_block: str) -> str:
    """Bloco injetado pra todos os volumes da serie casarem em paleta + luz."""
    return f"""

{_SERIES_BLOCK_HEADER} — match the other volumes of this series:
{series_block}
Keep the same palette and the same overall brightness/mood key as the rest of the
series. The SCENE above may differ per volume, but palette and lighting must read
as one cohesive collection."""


def _ensure_series_block(prompt: str, series_block: str | None) -> str:
    """Injeta o bloco de serie num prompt salvo se ainda nao tiver (idempotente).
    Usado pra re-alinhar capas antigas no regenerate sem re-derivar a ancora."""
    if not series_block or _SERIES_BLOCK_HEADER in prompt:
        return prompt
    return prompt + _series_consistency_block(series_block)


# Tabela compacta de cores nomeadas (nome -> RGB) pra traduzir os tons dominantes
# da 1a capa em palavras que o Gemini entende (ele ignora hex, mas responde a nomes).
_NAMED_COLORS: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("black", (15, 15, 18)), ("charcoal", (45, 45, 50)), ("slate grey", (90, 95, 105)),
    ("ash grey", (150, 150, 155)), ("white", (240, 240, 238)), ("cream", (235, 222, 195)),
    ("deep crimson", (120, 25, 30)), ("crimson red", (190, 40, 45)), ("ember orange", (210, 95, 40)),
    ("amber gold", (215, 165, 60)), ("pale gold", (225, 205, 140)), ("olive green", (110, 120, 60)),
    ("forest green", (40, 95, 60)), ("emerald", (30, 150, 110)), ("teal", (35, 120, 130)),
    ("deep teal", (20, 70, 80)), ("sky blue", (120, 175, 215)), ("slate blue", (70, 95, 150)),
    ("deep indigo", (45, 45, 110)), ("midnight blue", (25, 30, 65)), ("royal purple", (95, 55, 145)),
    ("violet", (150, 110, 200)), ("magenta", (190, 60, 150)), ("rose pink", (220, 130, 160)),
    ("brown", (110, 75, 50)), ("tan", (180, 150, 110)),
)


def _nearest_color_name(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return min(
        _NAMED_COLORS,
        key=lambda nc: (nc[1][0] - r) ** 2 + (nc[1][1] - g) ** 2 + (nc[1][2] - b) ** 2,
    )[0]


def _extract_series_anchor(raw_bytes: bytes, k: int = 5) -> str:
    """Deriva a ancora de coesao (paleta + chave de luz) da arte CRUA da 1a capa.
    Deterministico, Pillow puro (zero IA). Devolve uma string curta pro prompt."""
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    img.thumbnail((256, 384))

    # Chave de luz pela luminancia media (escuro/medio/claro) — e o que mais varia
    # entre volumes e o que precisamos travar.
    gray = img.convert("L")
    pixels = list(gray.getdata())
    mean_lum = sum(pixels) / len(pixels) if pixels else 128
    if mean_lum < 85:
        lighting = "dark, low-key lighting with deep shadows"
    elif mean_lum < 170:
        lighting = "balanced mid-key lighting"
    else:
        lighting = "bright, high-key lighting"

    # Paleta: tons dominantes → nomes (dedup preservando ordem de frequencia).
    quant = img.quantize(colors=k, method=Image.MEDIANCUT)
    palette = quant.getpalette() or []
    color_counts = sorted(quant.getcolors() or [], reverse=True)  # [(count, idx), ...]
    names: list[str] = []
    for _count, idx in color_counts:
        rgb = (palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2])
        name = _nearest_color_name(rgb)
        if name not in names:
            names.append(name)
    palette_str = ", ".join(names[:5]) or "muted neutral tones"
    return f"Palette: {palette_str}. Lighting: {lighting}."


def _build_image_prompt(
    novel_meta: NovelMeta,
    volume_title: str | None,
    brief: _Brief,
    style_override: str | None = None,
    series_block: str | None = None,
) -> str:
    title_clause = (
        f"for the volume \"{volume_title}\" of the web novel series \"{novel_meta.title}\""
        if volume_title
        else f"for the web novel \"{novel_meta.title}\""
    )
    # Estilo escolhido pelo usuario domina a direcao de arte. Sem escolha, usa a
    # `style` que o modelo de texto inferiu do conteudo (comportamento padrao).
    art_direction = style_override or brief.style
    # A linha "Painterly digital illustration. Cinematic..." e opinativa demais e
    # briga com estilos como Flat/Minimalist/Cyberpunk — so a aplicamos no modo
    # automatico. Com estilo escolhido, o proprio `style_override` manda no look.
    medium_line = (
        "" if style_override else "\n- Painterly digital illustration. Cinematic, atmospheric lighting."
    )
    # Coesao de serie (paleta + luz) entre ART DIRECTION e COMPOSITION — a cena varia,
    # mas a paleta/luz seguem a 1a capa. Anti-texto (CRITICAL) continua por ultimo.
    series_clause = _series_consistency_block(series_block) if series_block else ""
    return f"""A dramatic book cover illustration {title_clause}.

SCENE TO DEPICT: {brief.scene}

ART DIRECTION: {art_direction}{series_clause}

COMPOSITION:
- Portrait orientation, 2:3 aspect ratio (vertical book cover).
- One strong focal subject. Rule of thirds composition.{medium_line}
- Rich detail without clutter.
- Keep the lower third calmer and less busy (no faces or critical detail at the
  very bottom) — a title bar is added there afterwards.

ABSOLUTELY NO TEXT — THIS IS CRITICAL:
- Do NOT render any letters, words, numbers, titles, the series name, captions,
  signatures, watermarks, logos, frames, borders, or UI elements.
- The title and series name are composited separately AFTER generation — if you
  draw any text it will collide with it and look broken.
- If the scene would naturally include text (book spines, signs, banners, runes
  as letters), leave those surfaces blank or use abstract non-letter marks.
- Output a PURE, 100% TEXTLESS illustration."""


async def _build_visual_brief(
    *,
    client: genai.Client,
    text_model: str,
    novel_id: int,
    novel_meta: NovelMeta,
    volume_title: str | None,
    chapters: list[ChapterContent],
    glossary: list[GlossaryEntry],
    style_hint: str | None = None,
) -> _Brief:
    excerpts = _sample_chapters(chapters)
    user_prompt = _build_brief_user_prompt(
        novel_meta, volume_title, excerpts, glossary, style_hint
    )
    config = types.GenerateContentConfig(
        system_instruction=_BRIEF_SYSTEM,
        response_mime_type="application/json",
        response_schema=_Brief,
        temperature=0.6,
    )
    resp = await call_with_retry(
        lambda: client.aio.models.generate_content(
            model=text_model, contents=user_prompt, config=config
        ),
        op="cover_brief",
    )
    brief: _Brief = resp.parsed  # type: ignore[assignment]
    # Custo do brief (texto curto, ~$0.0001/call mas pra contar tudo)
    usage = getattr(resp, "usage_metadata", None)
    UsageStore().record(
        op="cover_brief", model=text_model,
        input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        novel_id=novel_id,
    )
    log.info(
        "cover_brief_built",
        scene=brief.scene[:140],
        style=brief.style[:80],
        excerpts=len(excerpts),
    )
    return brief


async def _generate_image_bytes(
    *,
    client: genai.Client,
    image_model: str,
    prompt: str,
    novel_id: int,
    aspect_ratio: str = "2:3",
    image_size: str = "2K",
) -> tuple[bytes, str]:
    """Chama o Gemini image model e extrai os bytes da imagem.

    Aspect ratio 2:3 e resolucao 2K dao ~1408x2112 (portrait), proximo da
    recomendacao Amazon p/ capa Kindle (1600x2560, ratio 1.6:1). O prompt em
    `_build_image_prompt` ja pede portrait mas o modelo ignora — precisa do
    `image_config` explicito. ``aspect_ratio`` permite gerar wallpapers nativos
    (ex: "9:16", "16:9") com o mesmo conteudo.
    """
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        temperature=0.9,
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        ),
    )
    resp = await call_with_retry(
        lambda: client.aio.models.generate_content(
            model=image_model, contents=prompt, config=config
        ),
        op="cover_image",
        max_attempts=4,  # gen de imagem custa $0.04, sopa de menos retry
    )

    # A imagem vem como Part com inline_data
    candidates = getattr(resp, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if content is None:
            continue
        for part in content.parts or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                # Registra custo (por-imagem, ~$0.039)
                UsageStore().record(
                    op="cover_image", model=image_model,
                    input_tokens=0, output_tokens=0,
                    novel_id=novel_id,
                )
                return inline.data, inline.mime_type or "image/png"

    raise CoverGenError("Gemini nao devolveu imagem (resposta vazia ou bloqueada)")


async def generate_or_cache_cover(
    *,
    novel_id: int,
    novel_meta: NovelMeta,
    volume_title: str | None,
    chapters: list[ChapterContent],
    glossary: list[GlossaryEntry],
    cover_style: str | None = None,
    text_model: str = "gemini-2.5-flash",
    image_model: str = "gemini-2.5-flash-image",
) -> tuple[bytes, str]:
    """Retorna ``(image_bytes, mime)``. Usa cache se existir, senao gera + salva.

    ``cover_style`` e o id de um estilo de arte (ver ``cover_styles.COVER_STYLES``);
    None/desconhecido = a IA decide o estilo a partir do conteudo (padrao)."""
    cache = CoverCache()
    cached = cache.get(novel_id, volume_title)
    if cached is not None:
        log.info("cover_cache_hit", novel_id=novel_id, volume_title=volume_title)
        return cached

    novel_row = ChapterCache().get_novel(novel_id)
    # Consistencia de serie: sem estilo explicito, herda o estilo-padrao da novel
    # (gravado numa escolha anterior). Assim todos os volumes nascem coerentes em
    # vez da IA escolher uma estetica diferente pra cada um.
    if not cover_style and novel_row and novel_row.get("default_cover_style"):
        cover_style = novel_row["default_cover_style"]
        log.info("cover_style_from_novel_default", novel_id=novel_id, style=cover_style)

    # Ancora de serie (paleta + luz): se ja existe e foi construida pro mesmo
    # estilo efetivo, injeta no prompt; senao, esta capa vai ESTABELECE-la (a
    # ancora e extraida da imagem desta capa, depois de gerada).
    effective_style = cover_style or None
    existing_anchor = novel_row.get("series_palette") if novel_row else None
    anchor_style = (novel_row.get("series_anchor_style") if novel_row else None) or None
    anchor_fresh = bool(existing_anchor) and anchor_style == effective_style
    series_block = existing_anchor if anchor_fresh else None
    must_establish = not anchor_fresh

    style_override = style_prompt(cover_style)
    client = genai.Client(api_key=_resolve_api_key())
    brief = await _build_visual_brief(
        client=client,
        text_model=text_model,
        novel_id=novel_id,
        novel_meta=novel_meta,
        volume_title=volume_title,
        chapters=chapters,
        glossary=glossary,
        style_hint=style_override,
    )
    prompt = _build_image_prompt(novel_meta, volume_title, brief, style_override, series_block)
    raw_bytes, raw_mime = await _generate_image_bytes(
        client=client, image_model=image_model, prompt=prompt, novel_id=novel_id,
    )

    # 1a capa (ou apos troca de estilo): ESTABELECE a ancora a partir desta imagem
    # crua e re-embute o bloco no prompt salvo (string, custo zero) pra regerar essa
    # capa manter a coleção. A imagem ja gerada NAO e refeita (ela define a ancora).
    if must_establish:
        series_block = _extract_series_anchor(raw_bytes)
        ChapterCache().set_series_anchor(novel_id, series_block, effective_style)
        prompt = _build_image_prompt(novel_meta, volume_title, brief, style_override, series_block)
        log.info("series_anchor_established", novel_id=novel_id, anchor=series_block[:120])

    # Composite tipografia POR CIMA (Gemini Image erra texto — typos, letras
    # tortas). Fica salvo no cache ja com o titulo aplicado, entao a capa
    # servida pro EPUB ja vem completa.
    final_bytes, final_mime = _composite_title_overlay(
        raw_bytes,
        novel_title=novel_meta.title,
        volume_title=volume_title,
        mime=raw_mime,
    )
    cache.save(
        novel_id=novel_id,
        volume_title=volume_title,
        image_data=final_bytes,
        image_data_raw=raw_bytes,  # arte sem texto, pra galeria/wallpapers
        mime_type=final_mime,
        prompt=prompt,
        model=image_model,
    )
    log.info(
        "cover_generated",
        novel_id=novel_id,
        volume_title=volume_title,
        bytes=len(final_bytes),
        mime=final_mime,
        raw_bytes=len(raw_bytes),
    )
    return final_bytes, final_mime


def _wallpaper_prompt(base_prompt: str, aspect: str) -> str:
    """Adapta o prompt da capa pra um wallpaper full-bleed na proporcao dada.
    Mantem cena + direcao de arte; tira o enquadramento de 'capa de livro'."""
    orientation = "vertical" if aspect == "9:16" else "horizontal"
    return (
        base_prompt
        + f"\n\nRENDER AS A FULL-BLEED {orientation.upper()} WALLPAPER ({aspect}): "
        "fill the entire frame edge to edge, recomposing/extending the scene "
        "naturally to fit the wider canvas. No book-cover framing, no spine, no "
        "borders, no margins, no text. Pure illustration."
    )


async def generate_native_wallpaper(
    *,
    cover_id: int,
    fmt: str,
    image_model: str = "gemini-2.5-flash-image",
) -> tuple[bytes, str]:
    """Gera (via Gemini, PAGO ~$0.04) um wallpaper nativo na proporcao do ``fmt``
    ('phone'|'pc'), reusando o prompt da capa. Cacheia em GeneratedCoverVariant.
    """
    from app.image_gen.wallpaper import ASPECT_BY_FORMAT

    aspect = ASPECT_BY_FORMAT.get(fmt)
    if aspect is None:
        raise CoverGenError(f"formato de wallpaper desconhecido: {fmt}")

    cache = CoverCache()
    cached = cache.get_variant(cover_id, aspect)
    if cached is not None:
        return cached

    row = cache.get_by_id(cover_id)
    if row is None:
        raise CoverGenError("capa nao encontrada")

    client = genai.Client(api_key=_resolve_api_key())
    prompt = _wallpaper_prompt(row["prompt"], aspect)
    img_bytes, mime = await _generate_image_bytes(
        client=client,
        image_model=image_model,
        prompt=prompt,
        novel_id=row["novel_id"],
        aspect_ratio=aspect,
    )
    cache.save_variant(
        cover_id=cover_id, aspect=aspect, image_data=img_bytes, mime_type=mime
    )
    log.info("wallpaper_native_generated", cover_id=cover_id, aspect=aspect, bytes=len(img_bytes))
    return img_bytes, mime


async def regenerate_cover_art(
    *,
    cover_id: int,
    image_model: str = "gemini-2.5-flash-image",
) -> tuple[bytes, str]:
    """Re-gera a arte (via Gemini, PAGO ~$0.04) REUSANDO o prompt salvo da capa.

    Usado pra liberar a "arte sem texto" em capas antigas (geradas antes de
    salvarmos a versao crua). A cena/estilo ficam iguais (mesmo prompt), mas e
    uma geracao nova. Salva raw + recompoe o titulo por cima. Retorna a versao
    com titulo ``(bytes, mime)``.
    """
    cache = CoverCache()
    row = cache.get_by_id(cover_id)
    if row is None:
        raise CoverGenError("capa nao encontrada")

    novel = ChapterCache().get_novel(row["novel_id"])
    if novel is None:
        raise CoverGenError("novel da capa nao encontrada")

    # Re-alinha com a coleção: se a novel ja tem ancora de serie e o prompt salvo
    # (capa antiga) ainda nao tinha o bloco, injeta agora — sem re-derivar (custo zero).
    prompt = _ensure_series_block(row["prompt"], novel.get("series_palette"))

    client = genai.Client(api_key=_resolve_api_key())
    raw_bytes, raw_mime = await _generate_image_bytes(
        client=client, image_model=image_model, prompt=prompt,
        novel_id=row["novel_id"],
    )
    final_bytes, final_mime = _composite_title_overlay(
        raw_bytes,
        novel_title=novel["title"],
        volume_title=row["volume_title"],
        mime=raw_mime,
    )
    cache.save(
        novel_id=row["novel_id"],
        volume_title=row["volume_title"],
        image_data=final_bytes,
        image_data_raw=raw_bytes,
        mime_type=final_mime,
        prompt=prompt,
        model=image_model,
    )
    log.info("cover_art_regenerated", cover_id=cover_id, bytes=len(final_bytes))
    return final_bytes, final_mime
