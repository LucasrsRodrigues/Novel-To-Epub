"""Persistencia de volumes EPUB gerados (lista da biblioteca por novel)."""

from __future__ import annotations

from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db


class VolumeStore:
    def __init__(self) -> None:
        init_db()

    def save_completed(
        self,
        *,
        novel_id: int,
        source_url: str,
        volume_title: str | None,
        start: int,
        end: int | None,
        with_cover: bool,
        ai_cover: bool,
        translate_to: str | None,
        output_path: str,
        translation_failed: int,
    ) -> int:
        """Upsert por (novel_id, output_path). Devolve o id do volume."""
        with get_session() as s:
            row = s.scalar(
                select(orm.GeneratedVolume).where(
                    orm.GeneratedVolume.novel_id == novel_id,
                    orm.GeneratedVolume.output_path == output_path,
                )
            )
            if row is None:
                row = orm.GeneratedVolume(
                    novel_id=novel_id,
                    output_path=output_path,
                    source_url=source_url,
                )
                s.add(row)
            row.volume_title = volume_title
            row.start_chapter = start
            row.end_chapter = end
            row.with_cover = with_cover
            row.ai_cover = ai_cover
            row.translate_to = translate_to
            row.translation_failed = translation_failed
            row.source_url = source_url
            s.commit()
            s.refresh(row)
            return row.id

    def list_for_novel(self, novel_id: int) -> list[dict]:
        """Volumes gerados desta novel, mais novos primeiro."""
        with get_session() as s:
            rows = s.scalars(
                select(orm.GeneratedVolume)
                .where(orm.GeneratedVolume.novel_id == novel_id)
                .order_by(orm.GeneratedVolume.created_at.desc())
            ).all()
            return [_to_dict(r) for r in rows]

    def get(self, volume_id: int) -> dict | None:
        with get_session() as s:
            row = s.get(orm.GeneratedVolume, volume_id)
            return _to_dict(row) if row else None


def _to_dict(row: orm.GeneratedVolume) -> dict:
    return {
        "id": row.id,
        "novel_id": row.novel_id,
        "volume_title": row.volume_title,
        "start": row.start_chapter,
        "end": row.end_chapter,
        "with_cover": row.with_cover,
        "ai_cover": row.ai_cover,
        "translate_to": row.translate_to,
        "output_path": row.output_path,
        "translation_failed": row.translation_failed,
        "source_url": row.source_url,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
