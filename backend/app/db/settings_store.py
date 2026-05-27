"""Repositorio das configuracoes editaveis (persistidas no SQLite, linha id=1)."""

from __future__ import annotations

from app.db import models as orm
from app.db.database import get_session, init_db

_FIELDS = (
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "smtp_use_tls",
    "smtp_from",
    "kindle_email",
    "gemini_api_key",
    "target_language",
    "translation_model",
    # Cascade providers
    "groq_api_key",
    "openrouter_api_key",
    "cerebras_api_key",
    "groq_model",
    "openrouter_model",
    "cerebras_model",
    "cascade_order",
)


def _to_dict(row: orm.AppSettings) -> dict:
    return {f: getattr(row, f) for f in _FIELDS}


class SettingsStore:
    def __init__(self) -> None:
        init_db()

    def get(self) -> dict:
        with get_session() as s:
            row = s.get(orm.AppSettings, 1)
            if row is None:
                row = orm.AppSettings(id=1)
                s.add(row)
                s.commit()
            return _to_dict(row)

    def update(self, data: dict) -> dict:
        """Patch: aplica apenas as chaves presentes em ``data``."""
        with get_session() as s:
            row = s.get(orm.AppSettings, 1)
            if row is None:
                row = orm.AppSettings(id=1)
                s.add(row)
            for key, value in data.items():
                if key in _FIELDS:
                    setattr(row, key, value)
            s.commit()
            return _to_dict(row)
