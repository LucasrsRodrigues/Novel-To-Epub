"""Rebuild de EPUB sem re-traduzir nem re-baixar.

Caso de uso: usuario editou um capitulo manualmente, ou mexemos no builder
(CSS, layout do TOC, capa), ou um EPUB sumiu do disco. Rebuild monta o
arquivo de novo usando 100% do que ja esta no SQLite — zero token de Gemini,
zero request HTTP (exceto eventual fallback de capa raspada).
"""

from __future__ import annotations

from pathlib import Path

from slugify import slugify

from app.db.cache import ChapterCache
from app.db.cover_cache import CoverCache
from app.db.database import get_session
from app.db import models as orm
from app.db.volume_store import VolumeStore
from app.epub.builder import build_epub
from app.logging_conf import get_logger
from app.models import ChapterContent, NovelMeta
from app.scraper.http import HttpClient
from app.translation.translation_store import TranslationStore

log = get_logger("rebuild")


class RebuildError(RuntimeError):
    pass


async def rebuild_volume_epub(volume_id: int) -> Path:
    """Re-monta o EPUB de um volume persistido a partir do cache.

    Atualiza ``GeneratedVolume`` (translation_failed pode ter mudado se o
    usuario adicionou traduções manuais). Devolve o path do .epub novo
    (mesmo do antigo — sobrescreve).
    """
    vs = VolumeStore()
    vol = vs.get(volume_id)
    if vol is None:
        raise RebuildError(f"volume {volume_id} nao existe")

    novel_id = vol["novel_id"]
    cache = ChapterCache()
    novel_dict = cache.get_novel(novel_id)
    if novel_dict is None:
        raise RebuildError(f"novel {novel_id} sumiu do cache")

    # Reconstroi NovelMeta sem `chapters` (build_epub nao precisa da lista
    # completa — usa `chapters` parametro).
    meta = NovelMeta(
        title=novel_dict["title"],
        author=novel_dict["author"],
        description=novel_dict["description"],
        source_url=novel_dict["source_url"],
        cover_url=novel_dict["cover_url"],
        chapters=[],
    )

    # ---- Coleta capitulos do range no cache (+ traducao se aplicavel) ----
    start = vol["start"]
    end = vol["end"]
    translate_to = vol["translate_to"]
    translation_store = TranslationStore() if translate_to else None

    collected: list[ChapterContent] = []
    missing: list[int] = []
    translation_failed = 0

    # Resolve fim quando `end` e None (= "ate o final do cache disponivel")
    if end is None:
        cached = sorted(cache.cached_indices(novel_id))
        if not cached:
            raise RebuildError(f"novel {novel_id} sem capitulos em cache")
        end = max(cached)

    for idx in range(start, end + 1):
        ch = cache.get_chapter(novel_id, idx)
        if ch is None:
            missing.append(idx)
            continue
        if translation_store is not None:
            t = translation_store.get(novel_id, idx, translate_to)
            if t is not None:
                t_html, t_title = t
                ch = ChapterContent(
                    index=ch.index, title=t_title or ch.title, html=t_html, url=ch.url,
                )
            else:
                # Cap sem traducao salva — fica em EN (mesma estrategia do
                # orchestrator). Conta como falha pra UI sinalizar.
                translation_failed += 1
        collected.append(ch)

    if not collected:
        raise RebuildError(
            f"volume {volume_id} sem capitulos disponiveis no cache "
            f"(missing={missing[:10]})"
        )
    if missing:
        log.warning(
            "rebuild_missing_chapters",
            volume_id=volume_id, count=len(missing),
            sample=missing[:10],
        )

    # ---- Capa ----
    cover_bytes: bytes | None = None
    if vol["ai_cover"]:
        cached_cover = CoverCache().get(novel_id, vol["volume_title"])
        if cached_cover is not None:
            cover_bytes, _ = cached_cover
        else:
            log.warning("rebuild_ai_cover_missing", volume_id=volume_id)
    if cover_bytes is None and vol["with_cover"] and meta.cover_url:
        # Fallback: re-baixa raspada (1 request HTTP, sem token Gemini)
        try:
            async with HttpClient() as client:
                cover_bytes = await client.get_bytes(meta.cover_url)
        except Exception as exc:
            log.warning("rebuild_cover_fetch_failed", error=str(exc))

    # ---- Build ----
    out_path = Path(vol["output_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    epub_lang = translate_to or "en"
    build_epub(
        meta, collected, out_path,
        cover_bytes=cover_bytes, language=epub_lang,
        epub_title=vol["volume_title"],
    )

    # Atualiza translation_failed (pode ter diminuido se usuario traduziu manual)
    vs.save_completed(
        novel_id=novel_id,
        source_url=vol["source_url"],
        volume_title=vol["volume_title"],
        start=start,
        end=end,
        with_cover=vol["with_cover"],
        ai_cover=vol["ai_cover"],
        translate_to=translate_to,
        output_path=str(out_path),
        translation_failed=translation_failed,
    )

    log.info(
        "rebuild_complete",
        volume_id=volume_id, path=str(out_path),
        chapters=len(collected), translation_failed=translation_failed,
        missing=len(missing),
    )
    return out_path
