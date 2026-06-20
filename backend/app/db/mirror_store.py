"""Persistencia das fontes alternativas (mirrors) de uma novel.

Cada mirror e um (adapter, url) que aponta pra MESMA obra em outro site. O
orchestrator usa a lista (ordenada por prioridade) pra cair pra outra fonte
quando o primario falha num capitulo — ver ``app.orchestrator``.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db


def _to_dict(row: orm.NovelMirror) -> dict:
    return {
        "id": row.id,
        "novel_id": row.novel_id,
        "source": row.source,
        "source_url": row.source_url,
        "priority": row.priority,
    }


class MirrorStore:
    def __init__(self) -> None:
        init_db()

    def add(self, novel_id: int, source: str, source_url: str) -> dict:
        """Adiciona (ou devolve o existente) um mirror pra novel. Idempotente
        por (novel_id, source_url)."""
        with get_session() as s:
            row = s.scalar(
                select(orm.NovelMirror).where(
                    orm.NovelMirror.novel_id == novel_id,
                    orm.NovelMirror.source_url == source_url,
                )
            )
            if row is None:
                row = orm.NovelMirror(
                    novel_id=novel_id, source=source, source_url=source_url
                )
                s.add(row)
                s.commit()
            return _to_dict(row)

    def list_for_novel(self, novel_id: int) -> list[dict]:
        """Mirrors da novel, ordenados por prioridade (menor primeiro)."""
        with get_session() as s:
            rows = s.scalars(
                select(orm.NovelMirror)
                .where(orm.NovelMirror.novel_id == novel_id)
                .order_by(orm.NovelMirror.priority, orm.NovelMirror.id)
            ).all()
            return [_to_dict(r) for r in rows]

    def delete(self, mirror_id: int) -> bool:
        with get_session() as s:
            row = s.get(orm.NovelMirror, mirror_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True
