"""Orquestra traducao de UM capitulo: cache → provider → glossario → cache."""

from __future__ import annotations

import re

from app.logging_conf import get_logger
from app.translation.glossary import GlossaryEntry, GlossaryStore
from app.translation.provider import TranslationProvider
from app.translation.style import (
    StyleProfileStore,
    build_anchor_block,
    extract_profile_from_text,
    fetch_style_anchor,
)
from app.translation.translation_store import TranslationStore
from app.translation.wiki_lookup import WikiClient

log = get_logger("translator")


def _infer_gender_from_pronouns(text: str) -> str | None:
    """Heuristica: conta pronomes na introducao da wiki."""
    t = " " + text.lower() + " "
    male = sum(t.count(p) for p in (" he ", " him ", " his "))
    female = sum(t.count(p) for p in (" she ", " her ", " hers "))
    if male >= 2 and male >= female * 2:
        return "male"
    if female >= 2 and female >= male * 2:
        return "female"
    return None


class Translator:
    def __init__(
        self,
        *,
        provider: TranslationProvider,
        target_language: str,
        glossary_store: GlossaryStore | None = None,
        translation_store: TranslationStore | None = None,
        wiki_client: WikiClient | None = None,
        style_store: StyleProfileStore | None = None,
        volume_title: str | None = None,
    ) -> None:
        self.provider = provider
        self.target = target_language
        self.gloss = glossary_store or GlossaryStore()
        self.trans = translation_store or TranslationStore()
        # passar wiki_client=False desliga; padrao = ativa
        self.wiki: WikiClient | None = (
            wiki_client if wiki_client is not None else WikiClient()
        )
        self.style = style_store or StyleProfileStore()
        # Volume atual — usado pra fetch do profile correto
        self._volume_title = volume_title

    async def translate(
        self,
        *,
        novel_id: int,
        novel_title: str,
        novel_slug: str | None,
        chapter_index: int,
        chapter_title: str,
        chapter_html: str,
    ) -> tuple[str, str, bool]:
        """Devolve ``(translated_title, translated_html, was_cached)``."""
        cached = self.trans.get(novel_id, chapter_index, self.target)
        if cached is not None:
            html, title = cached
            log.debug("translation_cache_hit", chapter=chapter_index)
            return title or chapter_title, html, True

        glossary = self.gloss.list_for_novel(novel_id)

        # Style profile (declarativo: tom, vocativo, etc) — só existe a partir
        # do 2º cap (1º cap "define" o estilo). E anchor: amostra do cap N-1.
        profile = self.style.get(novel_id, self._volume_title, self.target)
        profile_block = profile.to_prompt() if profile else ""
        anchor_sample = fetch_style_anchor(
            novel_id=novel_id, current_chapter=chapter_index, language=self.target,
        )
        anchor_block = build_anchor_block(anchor_sample)

        result = await self.provider.translate_chapter(
            text_html=chapter_html,
            chapter_title=chapter_title,
            target_language=self.target,
            glossary=glossary,
            novel_title=novel_title,
            novel_slug=novel_slug,
            chapter_index=chapter_index,
            style_profile_block=profile_block,
            style_anchor_block=anchor_block,
        )

        if result.new_entries:
            # Enriquece personagens ambiguos com info da wiki Fandom antes de salvar.
            if self.wiki is not None and novel_slug:
                await self._enrich_with_wiki(novel_id, novel_slug, result.new_entries)
            added, updated = self.gloss.upsert_many(
                novel_id, result.new_entries, first_seen_chapter=chapter_index
            )
            log.info("glossary_grew", chapter=chapter_index, added=added, updated=updated)

        self.trans.save(
            novel_id=novel_id,
            chapter_index=chapter_index,
            language=self.target,
            title=result.translated_title,
            html=result.translated_html,
            model=result.model,
            glossary_size=len(glossary),
        )

        # Define style profile do volume se ainda não tem (1º cap traduzido
        # define a "voz" — set é idempotente, preserva o 1º).
        if profile is None:
            inferred = extract_profile_from_text(result.translated_html)
            self.style.set(
                novel_id=novel_id,
                volume_title=self._volume_title,
                language=self.target,
                profile=inferred,
            )
            log.info(
                "style_profile_extracted",
                chapter=chapter_index,
                dialog=inferred.dialog_marker, person=inferred.second_person,
            )

        # Registra custo (dashboard)
        from app.db.usage_store import UsageStore
        UsageStore().record(
            op="translate_chapter", model=result.model,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            novel_id=novel_id, chapter_index=chapter_index,
        )

        return result.translated_title or chapter_title, result.translated_html, False

    async def _enrich_with_wiki(
        self,
        novel_id: int,
        novel_slug: str,
        entries: list[GlossaryEntry],
    ) -> None:
        """Busca na wiki APENAS personagens com gênero ambíguo ou baixa confiança.

        Se achar: anexa o resumo da wiki em ``notes`` e tenta inferir o gênero
        por contagem de pronomes (heurística simples mas eficaz para LitRPG).
        """
        assert self.wiki is not None
        targets = [
            e
            for e in entries
            if e.kind == "character" and (e.gender in ("unknown", "n/a") or e.confidence == "low")
        ]
        if not targets:
            return

        for entry in targets:
            info = await self.wiki.lookup(novel_id, novel_slug, entry.term)
            if not info["found"] or not info["summary"]:
                continue
            summary = info["summary"]
            inferred = _infer_gender_from_pronouns(summary)
            if inferred:
                entry.gender = inferred
                entry.confidence = "high"  # wiki + pronomes claros = confiavel
            # Anexa a info da wiki nas notes (sera vista em traducoes futuras).
            extra = f"[wiki] {summary[:300]}"
            entry.notes = (entry.notes + " " + extra).strip() if entry.notes else extra
            entry.source = "wiki"
            log.info(
                "wiki_enriched",
                term=entry.term,
                gender_inferred=inferred,
                summary_chars=len(summary),
            )
