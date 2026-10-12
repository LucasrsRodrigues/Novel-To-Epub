"""Dependencias e helpers compartilhados pelos routers da API."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.api.jobs import JobManager
from app.db.settings_store import SettingsStore
from app.kindle.sender import send_epub_to_kindle

_KINDLE_REQUIRED = ("smtp_host", "smtp_from", "kindle_email")


def get_jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def kindle_config() -> dict:
    """Config SMTP/Kindle salva; 400 se faltar o essencial pra enviar."""
    cfg = SettingsStore().get()
    missing = [k for k in _KINDLE_REQUIRED if not cfg.get(k)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"configuracao incompleta (faltam: {', '.join(missing)})",
        )
    return cfg


async def send_file_to_kindle(cfg: dict, path: str) -> None:
    """Envia um .epub pro Kindle com a config de ``kindle_config()``."""
    await send_epub_to_kindle(
        path,
        host=cfg["smtp_host"],
        port=cfg["smtp_port"],
        username=cfg["smtp_user"],
        password=cfg["smtp_password"],
        sender=cfg["smtp_from"],
        to=cfg["kindle_email"],
        use_tls=cfg["smtp_use_tls"],
    )
