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

from app.db.cover_cache import CoverCache
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
) -> str:
    excerpts_block = "\n\n".join(
        f"=== Capitulo {e.index} ===\n{e.text}" for e in excerpts
    )
    return f"""NOVEL: {novel_meta.title}
VOLUME: {volume_title or '(volume sem titulo definido)'}
DESCRICAO DA NOVEL:
{novel_meta.description or '(sem descricao)'}

GLOSSARIO (personagens / conceitos / termos chave):
{_glossary_summary(glossary)}

EXCERTOS DOS CAPITULOS COBERTOS:
{excerpts_block}

Produza o JSON com `scene` + `style`."""


def _build_image_prompt(
    novel_meta: NovelMeta,
    volume_title: str | None,
    brief: _Brief,
) -> str:
    title_clause = (
        f"for the volume \"{volume_title}\" of the web novel series \"{novel_meta.title}\""
        if volume_title
        else f"for the web novel \"{novel_meta.title}\""
    )
    return f"""A dramatic book cover illustration {title_clause}.

SCENE TO DEPICT: {brief.scene}

ART DIRECTION: {brief.style}

COMPOSITION:
- Portrait orientation, 2:3 aspect ratio (vertical book cover).
- One strong focal subject. Rule of thirds composition.
- Painterly digital illustration. Cinematic, atmospheric lighting.
- Rich detail without clutter.

STRICTLY DO NOT INCLUDE:
- Any text, letters, words, captions, titles, signatures, or watermarks.
- UI elements, frames, borders, logos.
- The output must be PURE illustration with zero typography."""


async def _build_visual_brief(
    *,
    client: genai.Client,
    text_model: str,
    novel_id: int,
    novel_meta: NovelMeta,
    volume_title: str | None,
    chapters: list[ChapterContent],
    glossary: list[GlossaryEntry],
) -> _Brief:
    excerpts = _sample_chapters(chapters)
    user_prompt = _build_brief_user_prompt(novel_meta, volume_title, excerpts, glossary)
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
) -> tuple[bytes, str]:
    """Chama o Gemini image model e extrai os bytes da imagem.

    Aspect ratio 2:3 e resolucao 2K dao ~1408x2112 (portrait), proximo da
    recomendacao Amazon p/ capa Kindle (1600x2560, ratio 1.6:1). O prompt em
    `_build_image_prompt` ja pede portrait mas o modelo ignora — precisa do
    `image_config` explicito.
    """
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        temperature=0.9,
        image_config=types.ImageConfig(
            aspect_ratio="2:3",  # portrait book cover
            image_size="2K",
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
    text_model: str = "gemini-2.5-flash",
    image_model: str = "gemini-2.5-flash-image",
) -> tuple[bytes, str]:
    """Retorna ``(image_bytes, mime)``. Usa cache se existir, senao gera + salva."""
    cache = CoverCache()
    cached = cache.get(novel_id, volume_title)
    if cached is not None:
        log.info("cover_cache_hit", novel_id=novel_id, volume_title=volume_title)
        return cached

    client = genai.Client(api_key=_resolve_api_key())
    brief = await _build_visual_brief(
        client=client,
        text_model=text_model,
        novel_id=novel_id,
        novel_meta=novel_meta,
        volume_title=volume_title,
        chapters=chapters,
        glossary=glossary,
    )
    prompt = _build_image_prompt(novel_meta, volume_title, brief)
    raw_bytes, raw_mime = await _generate_image_bytes(
        client=client, image_model=image_model, prompt=prompt, novel_id=novel_id,
    )
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
