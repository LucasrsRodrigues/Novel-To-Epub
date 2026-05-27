"""Cache de capas geradas por IA (BLOB no SQLite)."""

from __future__ import annotations

from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db


class CoverCache:
    def __init__(self) -> None:
        init_db()

    def get(self, novel_id: int, volume_title: str | None) -> tuple[bytes, str] | None:
        """Devolve ``(image_bytes, mime_type)`` ou None."""
        key = volume_title or ""
        with get_session() as s:
            row = s.scalar(
                select(orm.GeneratedCover).where(
                    orm.GeneratedCover.novel_id == novel_id,
                    orm.GeneratedCover.volume_title == key,
                )
            )
            return (row.image_data, row.mime_type) if row else None

    def delete(self, novel_id: int, volume_title: str | None) -> bool:
        """Remove cover do cache. Devolve True se removeu, False se nao existia."""
        key = volume_title or ""
        with get_session() as s:
            row = s.scalar(
                select(orm.GeneratedCover).where(
                    orm.GeneratedCover.novel_id == novel_id,
                    orm.GeneratedCover.volume_title == key,
                )
            )
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    def save(
        self,
        *,
        novel_id: int,
        volume_title: str | None,
        image_data: bytes,
        mime_type: str,
        prompt: str,
        model: str,
    ) -> None:
        key = volume_title or ""
        with get_session() as s:
            row = s.scalar(
                select(orm.GeneratedCover).where(
                    orm.GeneratedCover.novel_id == novel_id,
                    orm.GeneratedCover.volume_title == key,
                )
            )
            if row is None:
                row = orm.GeneratedCover(novel_id=novel_id, volume_title=key)
                s.add(row)
            row.image_data = image_data
            row.mime_type = mime_type
            row.prompt = prompt
            row.model = model
            s.commit()
