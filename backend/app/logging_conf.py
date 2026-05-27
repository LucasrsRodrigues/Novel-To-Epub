"""Configuracao de logging estruturado (structlog)."""

from __future__ import annotations

import logging

import structlog

from app.config import settings


def configure_logging(level: str | None = None, *, json: bool | None = None) -> None:
    """Configura structlog. Chamar uma vez no startup (CLI/API)."""
    level_name = (level or settings.log_level).upper()
    level_num = getattr(logging, level_name, logging.INFO)
    use_json = settings.log_json if json is None else json

    logging.basicConfig(format="%(message)s", level=level_num)

    # bibliotecas de rede sao ruidosas em INFO; so warnings delas
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
