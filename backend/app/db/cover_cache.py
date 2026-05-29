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
        image_data_raw: bytes | None = None,
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
            row.image_data_raw = image_data_raw
            row.mime_type = mime_type
            row.prompt = prompt
            row.model = model
            # Re-gerou a capa → variantes nativas antigas ficam obsoletas.
            row.variants.clear()
            s.commit()

    # ---------------------------------------------------------------- galeria
    def list_for_novel(self, novel_id: int) -> list[dict]:
        """Metadados (sem os BLOBs) das capas geradas de uma novel, pra galeria."""
        with get_session() as s:
            rows = s.scalars(
                select(orm.GeneratedCover)
                .where(orm.GeneratedCover.novel_id == novel_id)
                .order_by(orm.GeneratedCover.created_at.desc())
            ).all()
            return [
                {
                    "id": r.id,
                    "novel_id": r.novel_id,
                    "volume_title": r.volume_title or None,
                    "mime_type": r.mime_type,
                    "has_raw": r.image_data_raw is not None,
                    "native_aspects": sorted(v.aspect for v in r.variants),
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    def get_by_id(self, cover_id: int) -> dict | None:
        """Linha completa (com BLOBs + prompt) pra servir/derivar imagem."""
        with get_session() as s:
            r = s.get(orm.GeneratedCover, cover_id)
            if r is None:
                return None
            return {
                "id": r.id,
                "novel_id": r.novel_id,
                "volume_title": r.volume_title or None,
                "image_data": r.image_data,
                "image_data_raw": r.image_data_raw,
                "mime_type": r.mime_type,
                "prompt": r.prompt,
                "model": r.model,
            }

    # ------------------------------------------------------------- variantes
    def get_variant(self, cover_id: int, aspect: str) -> tuple[bytes, str] | None:
        with get_session() as s:
            v = s.scalar(
                select(orm.GeneratedCoverVariant).where(
                    orm.GeneratedCoverVariant.cover_id == cover_id,
                    orm.GeneratedCoverVariant.aspect == aspect,
                )
            )
            return (v.image_data, v.mime_type) if v else None

    def save_variant(
        self, *, cover_id: int, aspect: str, image_data: bytes, mime_type: str
    ) -> None:
        with get_session() as s:
            v = s.scalar(
                select(orm.GeneratedCoverVariant).where(
                    orm.GeneratedCoverVariant.cover_id == cover_id,
                    orm.GeneratedCoverVariant.aspect == aspect,
                )
            )
            if v is None:
                v = orm.GeneratedCoverVariant(cover_id=cover_id, aspect=aspect)
                s.add(v)
            v.image_data = image_data
            v.mime_type = mime_type
            s.commit()
