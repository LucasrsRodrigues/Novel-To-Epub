"""Orquestrador: amarra scraper + cache + builder de EPUB.

Fluxo de ``download_to_epub``:
  1. resolve o adapter pela URL
  2. ``fetch_novel`` -> metadados + lista de capitulos
  3. para cada capitulo no intervalo: usa o cache se ja tiver, senao baixa e
     salva (nunca rebaixa)
  4. baixa a capa
  5. gera o .epub

E I/O-bound e assincrono. O ``progress`` callback existe para a CLI (barra) e,
no futuro (Etapa 2), para o WebSocket.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from slugify import slugify

from app.config import settings
from app.db.cache import ChapterCache
from app.db.volume_store import VolumeStore
from app.epub.builder import build_epub
from app.logging_conf import get_logger
from app.models import ChapterContent, NovelMeta
from app.scraper.http import HttpClient
from app.scraper.registry import registry

log = get_logger("orchestrator")

# (stage, feito, total, titulo, veio_do_cache)
# stage: "download" | "translate"
ProgressCb = Callable[[str, int, int, str, bool], None]
# chamado uma vez assim que os metadados da novel ficam disponiveis
MetaCb = Callable[[NovelMeta], None]


async def download_to_epub(
    url: str,
    *,
    start: int = 1,
    end: int | None = None,
    output_dir: str | Path | None = None,
    with_cover: bool = True,
    progress: ProgressCb | None = None,
    on_meta: MetaCb | None = None,
    translate_to: str | None = None,
    volume_title: str | None = None,
    ai_cover: bool = False,
    on_complete: Callable[[dict], None] | None = None,
) -> Path:
    output_dir = Path(output_dir) if output_dir else settings.output_dir
    cache = ChapterCache()

    # Falha cedo se traducao foi pedida mas nenhum provider esta configurado,
    # pra nao desperdicar todo o download antes de descobrir. O translator REAL
    # (com novel_id+volume_title pro pin) é criado mais abaixo.
    if translate_to:
        from app.translation.factory import build_translator
        build_translator(target_language=translate_to)  # só valida configs

    async with HttpClient() as client:
        adapter = registry.resolve(url, client)
        meta = await adapter.fetch_novel(url)
        if on_meta:
            on_meta(meta)

        slug = meta.slug or slugify(meta.title)
        novel_id = cache.upsert_novel(adapter.name, slug, meta)

        # Translator real ja com novel_id+volume_title (cascade usa pra pin)
        translator = None
        if translate_to:
            from app.translation.factory import build_translator
            translator = build_translator(
                target_language=translate_to,
                novel_id=novel_id, volume_title=volume_title,
            )

        total = len(meta.chapters)
        if total == 0:
            raise RuntimeError(f"nenhum capitulo encontrado em {url}")
        last = total if end is None else min(end, total)
        refs = [r for r in meta.chapters if start <= r.index <= last]
        if not refs:
            raise ValueError(
                f"intervalo vazio (start={start}, end={end}, total={total})"
            )

        # ---- Fase 1: download / cache ----
        collected: list[ChapterContent] = []
        cached_count = 0
        for done, ref in enumerate(refs, start=1):
            chapter = cache.get_chapter(novel_id, ref.index)
            from_cache = chapter is not None
            if chapter is None:
                chapter = await adapter.fetch_chapter(ref)
                cache.save_chapter(novel_id, chapter)
            else:
                cached_count += 1
            collected.append(chapter)
            if progress:
                progress("download", done, len(refs), ref.title, from_cache)

        cover = None
        # Mesmo se ai_cover, baixa a raspada como fallback caso a IA falhe.
        if (with_cover or ai_cover) and meta.cover_url:
            try:
                cover = await client.get_bytes(meta.cover_url)
            except Exception as exc:  # capa e opcional; nao aborta o EPUB
                log.warning("cover_failed", url=meta.cover_url, error=str(exc))

    # ---- Fase 2: traducao (opcional) ----
    translated_count = 0
    # Por capitulo que falhou: {"chapter": int, "title": str, "reason": str}.
    # `reason` vem da mensagem da GeminiTranslationError (que ja inclui
    # finish_reason e block_reason) ou do str(exc) generico. UI mostra isso
    # no card de Downloads pro usuario entender por que cap X ficou em EN.
    translation_failures: list[dict] = []
    if translator is not None:
        translated: list[ChapterContent] = []
        for done, ch in enumerate(collected, start=1):
            try:
                t_title, t_html, was_cached = await translator.translate(
                    novel_id=novel_id,
                    novel_title=meta.title,
                    novel_slug=slug,
                    chapter_index=ch.index,
                    chapter_title=ch.title,
                    chapter_html=ch.html,
                )
                translated.append(
                    ChapterContent(index=ch.index, title=t_title, html=t_html, url=ch.url)
                )
                if was_cached:
                    translated_count += 1
                if progress:
                    progress("translate", done, len(collected), t_title, was_cached)
            except Exception as exc:
                # Falhou (safety filter, rate limit, json invalido, etc).
                # Mantem o capitulo ORIGINAL — usuario nao perde o volume e os
                # caps ja traduzidos ficam no cache. Re-rodar tenta de novo so
                # nos que falharam.
                reason = str(exc)[:500] or exc.__class__.__name__
                log.warning(
                    "translation_chapter_failed",
                    chapter=ch.index,
                    error=reason,
                )
                translation_failures.append(
                    {"chapter": ch.index, "title": ch.title, "reason": reason}
                )
                translated.append(ch)  # original (EN) inalterado
                if progress:
                    progress(
                        "translate",
                        done,
                        len(collected),
                        f"{ch.title} (falha — mantido em EN)",
                        False,
                    )
        collected = translated
        if translation_failures:
            log.warning(
                "translation_partial",
                failed_chapters=[f["chapter"] for f in translation_failures],
                failed_count=len(translation_failures),
                total=len(collected),
            )

    # ---- Fase 2.5: Capa por IA (opcional) — sobrescreve a raspada se OK ----
    if ai_cover:
        from app.image_gen.cover_generator import generate_or_cache_cover, CoverGenError
        from app.translation.glossary import GlossaryStore

        if progress:
            progress("cover", 0, 1, "gerando capa com IA...", False)
        try:
            glossary = GlossaryStore().list_for_novel(novel_id)
            ai_bytes, _mime = await generate_or_cache_cover(
                novel_id=novel_id,
                novel_meta=meta,
                volume_title=volume_title,
                chapters=collected,
                glossary=glossary,
            )
            cover = ai_bytes  # SUBSTITUI a raspada
            if progress:
                progress("cover", 1, 1, "capa pronta", False)
        except CoverGenError as exc:
            log.warning("ai_cover_skipped", reason=str(exc))
        except Exception as exc:
            log.warning("ai_cover_failed", error=str(exc))

    # ---- Fase 3: EPUB ----
    output_dir.mkdir(parents=True, exist_ok=True)
    lang_suffix = f"-{translate_to}" if translate_to else ""
    epub_lang = translate_to or "en"
    if volume_title:
        # Quando o usuario nomeou o volume (ex: "Volume 1 - O Sistema Vampirico"),
        # o arquivo recebe esse nome direto, sem prefixar com o slug da novel.
        filename = f"{slugify(volume_title)}{lang_suffix}.epub"
    else:
        filename = f"{slugify(meta.title)}-{start}-{last}{lang_suffix}.epub"
    path = output_dir / filename
    build_epub(
        meta,
        collected,
        path,
        cover_bytes=cover,
        language=epub_lang,
        epub_title=volume_title,
    )

    # Persiste o volume gerado pra biblioteca lembrar dele mesmo depois do
    # backend reiniciar (jobs sao in-memory). Upsert por (novel_id, output_path).
    volume_id = VolumeStore().save_completed(
        novel_id=novel_id,
        source_url=meta.source_url or url,
        volume_title=volume_title,
        start=start,
        end=last,
        with_cover=with_cover,
        ai_cover=ai_cover,
        translate_to=translate_to,
        output_path=str(path),
        translation_failed=len(translation_failures),
    )

    log.info(
        "download_complete",
        path=str(path),
        chapters=len(collected),
        from_cache=cached_count,
        downloaded=len(collected) - cached_count,
        translated_to=translate_to,
        translation_cache_hits=translated_count,
        translation_failures=len(translation_failures),
        volume_title=volume_title,
        ai_cover=ai_cover,
        volume_id=volume_id,
    )
    if on_complete:
        on_complete({
            "translation_failed_count": len(translation_failures),
            # Lista de dicts {chapter, title, reason} — UI mostra o motivo.
            "translation_failures": translation_failures,
            # Mantido p/ retrocompat (era list[int]); ninguem mais le, mas sem
            # custo manter.
            "translation_failed_chapters": [f["chapter"] for f in translation_failures],
            # Id no SQLite — UI usa pra endpoints baseados em volume (mais
            # robusto que job_id que mora so em memoria).
            "volume_id": volume_id,
        })
    return path
