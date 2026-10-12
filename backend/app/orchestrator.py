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
from app.db.mirror_store import MirrorStore
from app.db.volume_store import VolumeStore, novel_epub_dir
from app.epub.builder import build_epub
from app.logging_conf import get_logger
from app.models import ChapterContent, ChapterRef, NovelMeta
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
    cover_style: str | None = None,
    skip_chapters: list[int] | None = None,
    preserve_cover: bool = False,
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
        # Sinaliza pra UI que estamos buscando metadados ANTES de fetch_novel —
        # adapters como NovelFull paginam a TOC (~60 paginas) e nesse intervalo
        # o usuario fica olhando "0%" sem nada. Mostra ao menos o nome do adapter.
        if progress:
            progress("meta", 0, 0, f"Buscando lista de capítulos em {adapter.name}…", False)
            # Adapters que paginam podem reportar progresso granular ("pg 12/66")
            # via este callback opcional — propagamos pra mesma UI.
            adapter.on_meta_progress = lambda done, total, label: progress(
                "meta", done, total, label, False
            )
        meta = await adapter.fetch_novel(url)
        if on_meta:
            on_meta(meta)

        slug = meta.slug or slugify(meta.title)
        novel_id = cache.upsert_novel(adapter.name, slug, meta)

        # Escolha explicita de estilo vira o default desta novel (pre-selecionado
        # nas proximas capturas/regerar). "Automatico" (cover_style=None) NAO mexe
        # no default salvo — evita que fluxos como "traduzir no lugar" (que reusam
        # ai_cover mas nao passam estilo) apaguem a preferencia do usuario.
        if cover_style:
            cache.set_default_cover_style(novel_id, cover_style)

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
        skip_set = set(skip_chapters or [])
        refs = [
            r for r in meta.chapters if start <= r.index <= last and r.index not in skip_set
        ]
        if skip_set:
            log.info("chapters_skipped", skipped=sorted(skip_set), kept=len(refs))
        if not refs:
            raise ValueError(
                f"intervalo vazio (start={start}, end={end}, total={total})"
            )

        # ---- Fallback por mirror (Fatia 4) ----
        # Fontes alternativas desta novel. So sao tocadas se o primario falhar num
        # capitulo; a TOC de cada mirror e baixada UMA vez (lazy) e cacheada por
        # numero canonico de titulo — e por esse numero que casamos o cap entre
        # sites (a posicao diverge por off-by-N, o numero no titulo nao).
        mirror_configs = MirrorStore().list_for_novel(novel_id)
        mirror_adapters: dict[str, object] = {}
        mirror_tocs: dict[str, dict[int, ChapterRef]] = {}

        async def fetch_from_mirrors(ref: ChapterRef) -> tuple[ChapterContent, str] | None:
            """Tenta recuperar `ref` de cada mirror, casando por numero de titulo.
            Devolve (conteudo, nome_da_fonte) no 1o sucesso, ou None."""
            if ref.number is None or not mirror_configs:
                return None  # sem numero canonico nao da pra casar com seguranca
            for cfg in mirror_configs:
                m_url = cfg["source_url"]
                try:
                    adapter_m = mirror_adapters.get(m_url)
                    if adapter_m is None:
                        adapter_m = registry.resolve(m_url, client)
                        mirror_adapters[m_url] = adapter_m
                    toc = mirror_tocs.get(m_url)
                    if toc is None:
                        meta_m = await adapter_m.fetch_novel(m_url)
                        toc = {
                            r.number: r for r in meta_m.chapters if r.number is not None
                        }
                        mirror_tocs[m_url] = toc
                    target = toc.get(ref.number)
                    if target is None:
                        continue  # esse mirror nao tem esse numero
                    content = await adapter_m.fetch_chapter(target)
                    # Grava no slot do PRIMARIO (index), nao no do mirror.
                    content.index = ref.index
                    return content, cfg["source"]
                except Exception as exc:
                    log.warning(
                        "mirror_fetch_failed",
                        mirror=m_url,
                        chapter=ref.number,
                        error=str(exc)[:200],
                    )
                    continue
            return None

        # ---- Fase 1: download / cache ----
        collected: list[ChapterContent] = []
        cached_count = 0
        # Capitulos que nao deram pra baixar (404, DOM mudou, mirror quebrado...).
        # Em vez de derrubar o job inteiro — um cap quebrado != volume perdido —
        # registramos, pulamos e seguimos, igual as falhas de traducao. O EPUB sai
        # com o que deu certo e a UI mostra o que faltou (e por que). E a base do
        # fallback por mirror (Fatia 4): "se falhou aqui, tenta noutra fonte".
        download_failures: list[dict] = []
        for done, ref in enumerate(refs, start=1):
            chapter = cache.get_chapter(novel_id, ref.index)
            from_cache = chapter is not None
            label = ref.title
            if chapter is None:
                try:
                    chapter = await adapter.fetch_chapter(ref)
                except Exception as primary_exc:
                    # Primario falhou: tenta recuperar de uma fonte alternativa
                    # casando pelo numero canonico do titulo (Fatia 4).
                    recovered = await fetch_from_mirrors(ref)
                    if recovered is None:
                        reason = str(primary_exc)[:500] or primary_exc.__class__.__name__
                        log.warning(
                            "chapter_download_failed",
                            chapter=ref.index,
                            url=ref.url,
                            error=reason,
                        )
                        download_failures.append(
                            {"chapter": ref.index, "title": ref.title, "reason": reason}
                        )
                        if progress:
                            progress(
                                "download",
                                done,
                                len(refs),
                                f"{ref.title} (falha — pulado)",
                                False,
                            )
                        continue
                    chapter, via = recovered
                    label = f"{ref.title} · via {via}"
                    log.info(
                        "chapter_recovered_via_mirror",
                        chapter=ref.index,
                        number=ref.number,
                        mirror=via,
                    )
                cache.save_chapter(novel_id, chapter)
            else:
                cached_count += 1
            collected.append(chapter)
            if progress:
                progress("download", done, len(refs), label, from_cache)

        if not collected:
            # Todos falharam: sem isto o build geraria um EPUB vazio.
            raise RuntimeError(
                f"nenhum capitulo pôde ser baixado ({len(download_failures)} falharam)"
            )
        if download_failures:
            log.warning(
                "download_partial",
                failed_chapters=[f["chapter"] for f in download_failures],
                failed_count=len(download_failures),
                total=len(refs),
            )

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
    cover_error: str | None = None
    used_ai_cover = ai_cover
    if preserve_cover:
        # Recaptura mantendo a capa: reusa a capa já cacheada deste volume, sem
        # gerar nada (zero token) e sem tocar no cache. Se não houver capa
        # cacheada, mantém a raspada.
        from app.db.cover_cache import CoverCache

        cached_cover = CoverCache().get(novel_id, volume_title)
        if cached_cover is not None:
            cover = cached_cover[0]
            used_ai_cover = True  # o EPUB leva a capa IA preservada
            log.info("cover_preserved", novel_id=novel_id, volume_title=volume_title)
        else:
            log.info("cover_preserve_no_cache", novel_id=novel_id, volume_title=volume_title)
    elif ai_cover:
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
                cover_style=cover_style,
            )
            cover = ai_bytes  # SUBSTITUI a raspada
            if progress:
                progress("cover", 1, 1, "capa pronta", False)
        except CoverGenError as exc:
            cover_error = str(exc)
            log.warning("ai_cover_skipped", reason=cover_error)
        except Exception as exc:
            cover_error = str(exc)
            log.warning("ai_cover_failed", error=cover_error)
        # Falha de capa NAO derruba o job (o EPUB sai com a capa raspada), mas
        # agora o motivo e visivel na UI em vez de sumir num warning de log.
        if cover_error and progress:
            progress("cover", 1, 1, f"capa falhou: {cover_error[:120]}", False)

    # ---- Fase 3: EPUB ----
    epub_dir = novel_epub_dir(output_dir, slug)
    epub_dir.mkdir(parents=True, exist_ok=True)
    lang_suffix = f"-{translate_to}" if translate_to else ""
    epub_lang = translate_to or "en"
    if volume_title:
        # Quando o usuario nomeou o volume (ex: "Volume 1 - O Sistema Vampirico"),
        # o arquivo recebe esse nome direto, sem prefixar com o slug da novel —
        # a pasta da novel (epub_dir) e que separa obras com volumes homonimos.
        filename = f"{slugify(volume_title)}{lang_suffix}.epub"
    else:
        filename = f"{slugify(meta.title)}-{start}-{last}{lang_suffix}.epub"
    path = epub_dir / filename
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
        ai_cover=used_ai_cover,
        translate_to=translate_to,
        output_path=str(path),
        translation_failed=len(translation_failures),
        skip_chapters=sorted(skip_set),
    )

    log.info(
        "download_complete",
        path=str(path),
        chapters=len(collected),
        from_cache=cached_count,
        downloaded=len(collected) - cached_count,
        download_failures=len(download_failures),
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
            # Capitulos que nao puderam ser baixados (pulados, nao no EPUB).
            # Mesmo formato {chapter, title, reason}. UI mostra pro usuario saber
            # o que faltou e re-rodar (ou, na Fatia 4, cair pra outro mirror).
            "download_failed_count": len(download_failures),
            "download_failures": download_failures,
            # Mantido p/ retrocompat (era list[int]); ninguem mais le, mas sem
            # custo manter.
            "translation_failed_chapters": [f["chapter"] for f in translation_failures],
            # Motivo da falha de capa por IA (rate-limit, sem key, bloqueio...),
            # None se a capa saiu ok ou nao foi pedida. UI mostra pro usuario.
            "cover_error": cover_error,
            # Id no SQLite — UI usa pra endpoints baseados em volume (mais
            # robusto que job_id que mora so em memoria).
            "volume_id": volume_id,
        })
    return path
