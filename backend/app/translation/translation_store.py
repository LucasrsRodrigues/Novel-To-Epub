"""Cache de capitulos ja traduzidos. Nunca re-traduz o mesmo (novel, cap, lingua)."""

from __future__ import annotations

from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db


class TranslationStore:
    def __init__(self) -> None:
        init_db()

    def get(self, novel_id: int, chapter_index: int, language: str) -> tuple[str, str | None] | None:
        """Retorna ``(html, titulo_traduzido)`` ou ``None`` se nao houver."""
        with get_session() as s:
            row = s.scalar(
                select(orm.TranslatedChapter).where(
                    orm.TranslatedChapter.novel_id == novel_id,
                    orm.TranslatedChapter.chapter_index == chapter_index,
                    orm.TranslatedChapter.language == language,
                )
            )
            return (row.html, row.title) if row else None

    def save(
        self,
        *,
        novel_id: int,
        chapter_index: int,
        language: str,
        title: str | None,
        html: str,
        model: str,
        glossary_size: int,
    ) -> None:
        with get_session() as s:
            row = s.scalar(
                select(orm.TranslatedChapter).where(
                    orm.TranslatedChapter.novel_id == novel_id,
                    orm.TranslatedChapter.chapter_index == chapter_index,
                    orm.TranslatedChapter.language == language,
                )
            )
            if row is None:
                row = orm.TranslatedChapter(
                    novel_id=novel_id,
                    chapter_index=chapter_index,
                    language=language,
                )
                s.add(row)
            row.title = title
            row.html = html
            row.model = model
            row.glossary_size = glossary_size
            s.commit()
