"""Glossario por novel: dataclass de entrada + repositorio SQLite.

O glossario eh o coracao da traducao consistente: cada personagem mencionado
ganha uma entrada com genero, e o tradutor injeta isso no system prompt todo
capitulo. Sem isso, o modelo chuta genero a cada capitulo e contradiz a si
proprio em PT-BR (onde tudo eh marcado).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db

EntryKind = Literal["character", "place", "ability", "system_term", "other"]
Gender = Literal["male", "female", "non-binary", "unknown", "n/a"]
Confidence = Literal["high", "medium", "low"]
Source = Literal["llm", "wiki", "manual"]


@dataclass
class GlossaryEntry:
    term: str
    canonical_pt: str
    kind: str = "other"
    gender: str = "n/a"
    notes: str = ""
    confidence: str = "medium"
    first_seen_chapter: int | None = None
    source: str = "llm"


def _row_to_entry(row: orm.Glossary) -> GlossaryEntry:
    return GlossaryEntry(
        term=row.term,
        canonical_pt=row.canonical_pt,
        kind=row.kind,
        gender=row.gender,
        notes=row.notes or "",
        confidence=row.confidence,
        first_seen_chapter=row.first_seen_chapter,
        source=row.source,
    )


_CONF_RANK = {"high": 3, "medium": 2, "low": 1}


class GlossaryStore:
    def __init__(self) -> None:
        init_db()

    def list_for_novel(self, novel_id: int) -> list[GlossaryEntry]:
        with get_session() as s:
            rows = s.scalars(
                select(orm.Glossary)
                .where(orm.Glossary.novel_id == novel_id)
                .order_by(orm.Glossary.kind, orm.Glossary.term)
            ).all()
            return [_row_to_entry(r) for r in rows]

    def upsert_many(
        self,
        novel_id: int,
        entries: list[GlossaryEntry],
        *,
        first_seen_chapter: int | None = None,
    ) -> tuple[int, int]:
        """Insere os termos novos, atualiza os existentes.

        Politica: nao rebaixa confianca. Se ja temos uma entrada `high` e o LLM
        propos `low`, mantemos a high (e ignoramos a atualizacao). Edicao manual
        do usuario (source=manual) tambem nunca eh sobrescrita pelo LLM.

        Retorna ``(adicionadas, atualizadas)``.
        """
        added = updated = 0
        with get_session() as s:
            for entry in entries:
                row = s.scalar(
                    select(orm.Glossary).where(
                        orm.Glossary.novel_id == novel_id,
                        orm.Glossary.term == entry.term,
                    )
                )
                if row is None:
                    row = orm.Glossary(
                        novel_id=novel_id,
                        term=entry.term,
                        first_seen_chapter=first_seen_chapter,
                    )
                    s.add(row)
                    _apply(row, entry)
                    added += 1
                    continue

                if row.source == "manual":
                    continue  # nunca sobrescreve edicao manual
                if _CONF_RANK.get(entry.confidence, 0) < _CONF_RANK.get(row.confidence, 0):
                    continue  # nao rebaixa
                _apply(row, entry)
                updated += 1
            s.commit()
        return added, updated


def _apply(row: orm.Glossary, entry: GlossaryEntry) -> None:
    row.canonical_pt = entry.canonical_pt
    row.kind = entry.kind
    row.gender = entry.gender
    row.notes = entry.notes or ""
    row.confidence = entry.confidence
    row.source = entry.source
