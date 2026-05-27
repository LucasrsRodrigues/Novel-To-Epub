"""Style anchor + style profile — garante voz consistente entre caps/providers.

Anchor: pega últimos parágrafos do cap N-1 (TranslatedChapter) → injetado no
system prompt como referência viva de tom.

Profile: caracterização declarativa do estilo do volume (voice_tone, dialog_marker,
second_person, interjection_style). Extraído na 1ª tradução analisando o output;
nas próximas, injetado como instrução pro modelo manter coerência.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db
from app.logging_conf import get_logger
from app.translation.translation_store import TranslationStore

log = get_logger("style")


class StyleProfile(BaseModel):
    """Caracteriza o estilo de tradução escolhido pro volume."""

    voice_tone: str = Field(
        description="ex: 'narrativo formal', 'casual jovem', 'épico-poético'"
    )
    dialog_marker: str = Field(
        description="'travessão (—)' ou 'aspas (\"\")' — norma usada nos diálogos"
    )
    second_person: str = Field(
        description="'você' ou 'tu' — pronome de tratamento informal"
    )
    interjection_style: str = Field(
        default="",
        description="como traduzir interjeições recorrentes (ex: 'damn' → 'droga')",
    )

    def to_prompt(self) -> str:
        return f"""
PERFIL DE ESTILO DESTE VOLUME (cumpra rigorosamente — definido nos primeiros caps):
- Tom narrativo: {self.voice_tone}
- Marcação de diálogo: {self.dialog_marker}
- Pronome 2ª pessoa: {self.second_person}
{f"- Interjeições/palavrões: {self.interjection_style}" if self.interjection_style else ""}
"""


class StyleProfileStore:
    def __init__(self) -> None:
        init_db()

    def get(
        self, novel_id: int, volume_title: str | None, language: str
    ) -> StyleProfile | None:
        key = volume_title or ""
        with get_session() as s:
            row = s.scalar(
                select(orm.VolumeStyleProfile).where(
                    orm.VolumeStyleProfile.novel_id == novel_id,
                    orm.VolumeStyleProfile.volume_title == key,
                    orm.VolumeStyleProfile.language == language,
                )
            )
            if row is None:
                return None
            try:
                return StyleProfile.model_validate(json.loads(row.profile_json))
            except Exception as exc:
                log.warning("style_profile_corrupt", error=str(exc))
                return None

    def set(
        self,
        *,
        novel_id: int,
        volume_title: str | None,
        language: str,
        profile: StyleProfile,
    ) -> None:
        """Idempotente — preserva o 1º perfil (consistência)."""
        key = volume_title or ""
        with get_session() as s:
            existing = s.scalar(
                select(orm.VolumeStyleProfile).where(
                    orm.VolumeStyleProfile.novel_id == novel_id,
                    orm.VolumeStyleProfile.volume_title == key,
                    orm.VolumeStyleProfile.language == language,
                )
            )
            if existing is not None:
                return
            s.add(orm.VolumeStyleProfile(
                novel_id=novel_id, volume_title=key, language=language,
                profile_json=profile.model_dump_json(),
            ))
            s.commit()


# ---------------------------- Style Anchor (cap N-1) -----------------------


def _strip_html(html: str) -> str:
    """Texto cru pra style anchor (modelo lê melhor sem tags)."""
    text = re.sub(r"<[^>]+>", "\n", html)
    return re.sub(r"\n\s*\n", "\n\n", text).strip()


def fetch_style_anchor(
    *,
    novel_id: int,
    current_chapter: int,
    language: str,
    max_paragraphs: int = 3,
    max_chars: int = 900,
) -> str | None:
    """Retorna trecho dos últimos N parágrafos do cap N-1 traduzido (ou N-2 se N-1 falhou).

    Usado como amostra de "voz" no system prompt. None se não há cap anterior
    traduzido (vol acabou de começar) — sem anchor, modelo segue só o profile.
    """
    store = TranslationStore()
    # Tenta N-1 primeiro, depois N-2 (caso N-1 tenha ficado em EN por falha)
    for delta in (1, 2, 3):
        prev_idx = current_chapter - delta
        if prev_idx < 1:
            break
        got = store.get(novel_id, prev_idx, language)
        if got is None:
            continue
        html, _title = got
        text = _strip_html(html)
        # Últimos N parágrafos não vazios
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            continue
        sample = "\n\n".join(paragraphs[-max_paragraphs:])
        if len(sample) > max_chars:
            sample = "…" + sample[-max_chars:]
        return sample
    return None


def build_anchor_block(sample: str | None) -> str:
    if not sample:
        return ""
    return f"""
ÂNCORA DE ESTILO (amostra REAL do cap anterior — continue EXATAMENTE neste tom, ritmo e escolha de palavras):
─────
{sample}
─────
"""


# --------------------------- Heurística de extração ------------------------


def extract_profile_from_text(html: str) -> StyleProfile:
    """Detecta marcação de diálogo + pronome 2ª pessoa olhando o texto traduzido.

    Heurística leve (sem custo de LLM extra) — chamada após o 1º cap traduzido
    pra preencher o profile do volume. Padrões que pegam 90% dos casos:
      - Diálogo: linhas começando com "— " (travessão) vs com aspas "..." ou —
      - 2ª pessoa: contagem de "você" vs "tu " no texto
      - Tom: default "narrativo equilibrado" — usuario pode editar depois
    """
    text = _strip_html(html).lower()

    # Diálogo
    travessao_lines = sum(1 for ln in text.split("\n") if ln.strip().startswith("—"))
    quoted_lines = sum(
        1 for ln in text.split("\n")
        if (ln.strip().startswith('"') or ln.strip().startswith("“"))  # " ou “
    )
    if travessao_lines >= quoted_lines:
        dialog = "travessão (—)"
    else:
        dialog = 'aspas curvas (“”)'

    # 2ª pessoa
    voce = text.count(" você ") + text.count("você ")
    tu = text.count(" tu ") + text.count("tu ")
    second_person = "você" if voce >= tu else "tu"

    return StyleProfile(
        voice_tone="narrativo equilibrado",  # default; usuario pode editar
        dialog_marker=dialog,
        second_person=second_person,
        interjection_style="",
    )
