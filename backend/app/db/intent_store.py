"""Persistencia da intencao de captura (params de jobs nao concluidos).

Permite "Continuar captura" sobreviver ao restart do backend: jobs vivem em
memoria, mas estes registros guardam os params pra re-hidratar um job
interrompido/cancelado. Apagados quando o job conclui. Ver ``app.api.jobs``.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db


def _csv(indices: list[int] | None) -> str:
    return ",".join(str(i) for i in (indices or []))


def _parse_csv(s: str | None) -> list[int]:
    if not s:
        return []
    return [int(x) for x in s.split(",") if x.strip().isdigit()]


def _to_dict(row: orm.CaptureIntent) -> dict:
    return {
        "job_id": row.job_id,
        "source_url": row.source_url,
        "title": row.title,
        "start": row.start,
        "end": row.end,
        "with_cover": row.with_cover,
        "translate_to": row.translate_to,
        "volume_title": row.volume_title,
        "ai_cover": row.ai_cover,
        "cover_style": row.cover_style,
        "skip_chapters": _parse_csv(row.skip_chapters),
        "preserve_cover": row.preserve_cover,
        "replace_volume_id": row.replace_volume_id,
        "status": row.status,
    }


class IntentStore:
    def __init__(self) -> None:
        init_db()

    def upsert(
        self,
        *,
        job_id: str,
        source_url: str,
        title: str | None,
        start: int,
        end: int | None,
        with_cover: bool,
        translate_to: str | None,
        volume_title: str | None,
        ai_cover: bool,
        cover_style: str | None,
        skip_chapters: list[int] | None,
        preserve_cover: bool,
        replace_volume_id: int | None,
        status: str,
    ) -> None:
        with get_session() as s:
            row = s.scalar(
                select(orm.CaptureIntent).where(orm.CaptureIntent.job_id == job_id)
            )
            if row is None:
                row = orm.CaptureIntent(job_id=job_id)
                s.add(row)
            row.source_url = source_url
            row.title = title
            row.start = start
            row.end = end
            row.with_cover = with_cover
            row.translate_to = translate_to
            row.volume_title = volume_title
            row.ai_cover = ai_cover
            row.cover_style = cover_style
            row.skip_chapters = _csv(skip_chapters)
            row.preserve_cover = preserve_cover
            row.replace_volume_id = replace_volume_id
            row.status = status
            s.commit()

    def delete(self, job_id: str) -> None:
        with get_session() as s:
            row = s.scalar(
                select(orm.CaptureIntent).where(orm.CaptureIntent.job_id == job_id)
            )
            if row is not None:
                s.delete(row)
                s.commit()

    def list_all(self) -> list[dict]:
        with get_session() as s:
            rows = s.scalars(
                select(orm.CaptureIntent).order_by(orm.CaptureIntent.created_at)
            ).all()
            return [_to_dict(r) for r in rows]
