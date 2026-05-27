"""Pin de provider/modelo por volume — consistência intra-volume no cascade."""

from __future__ import annotations

from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db


class VolumePinStore:
    def __init__(self) -> None:
        init_db()

    def get(
        self, novel_id: int, volume_title: str | None, language: str
    ) -> tuple[str, str] | None:
        """Devolve (provider, model) pinado ou None."""
        key = volume_title or ""
        with get_session() as s:
            row = s.scalar(
                select(orm.VolumeTranslatorPin).where(
                    orm.VolumeTranslatorPin.novel_id == novel_id,
                    orm.VolumeTranslatorPin.volume_title == key,
                    orm.VolumeTranslatorPin.language == language,
                )
            )
            return (row.provider, row.model) if row else None

    def set(
        self,
        *,
        novel_id: int,
        volume_title: str | None,
        language: str,
        provider: str,
        model: str,
    ) -> None:
        """Pin idempotente — NAO sobrescreve se ja existe (preserva 1º que pegou)."""
        key = volume_title or ""
        with get_session() as s:
            existing = s.scalar(
                select(orm.VolumeTranslatorPin).where(
                    orm.VolumeTranslatorPin.novel_id == novel_id,
                    orm.VolumeTranslatorPin.volume_title == key,
                    orm.VolumeTranslatorPin.language == language,
                )
            )
            if existing is not None:
                return  # ja tem pin; respeita
            s.add(orm.VolumeTranslatorPin(
                novel_id=novel_id, volume_title=key, language=language,
                provider=provider, model=model,
            ))
            s.commit()

    def clear(self, novel_id: int, volume_title: str | None, language: str) -> bool:
        """Remove o pin (caller quer trocar de modelo deliberadamente)."""
        key = volume_title or ""
        with get_session() as s:
            row = s.scalar(
                select(orm.VolumeTranslatorPin).where(
                    orm.VolumeTranslatorPin.novel_id == novel_id,
                    orm.VolumeTranslatorPin.volume_title == key,
                    orm.VolumeTranslatorPin.language == language,
                )
            )
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True
