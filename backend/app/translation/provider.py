"""Interface abstrata do provedor de traducao (Gemini, OpenAI, local...)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.translation.glossary import GlossaryEntry


@dataclass
class TranslationResult:
    translated_html: str
    translated_title: str | None = None
    new_entries: list[GlossaryEntry] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class TranslationProvider(ABC):
    name: str = ""
    model: str = ""

    @abstractmethod
    async def translate_chapter(
        self,
        *,
        text_html: str,
        chapter_title: str,
        target_language: str,
        glossary: list[GlossaryEntry],
        novel_title: str,
        novel_slug: str | None = None,
        chapter_index: int | None = None,
        style_profile_block: str = "",
        style_anchor_block: str = "",
    ) -> TranslationResult:
        """Traduz um capitulo e propoe novas entradas pro glossario.

        `style_profile_block` e `style_anchor_block` são strings já formatadas
        (ou vazias) que o `Translator` (caller) monta a partir das stores. Caem
        no system prompt pra forçar consistência entre caps/providers.
        """
