"""Retry com backoff exponencial pra chamadas da Gemini API.

Erros transitorios mais comuns:
  - 503 UNAVAILABLE — "high demand", pico de carga
  - 429 RESOURCE_EXHAUSTED — rate limit (free tier costuma bater)
  - 500 / 502 / 504 — falhas internas/proxy/timeout do GCP
  - 408 — request timeout

Erros permanentes (NAO fazem retry): 400 (request malformado), 401 (auth),
403 (permissao), 404 (modelo nao existe).

Timeout do client (``GEMINI_TIMEOUT_S``) tambem NAO faz retry: cada tentativa ja
esperou minutos, e repetir 5x seguraria a fila por ~15min. Vira
``GeminiTimeoutError`` (mensagem legivel) e quem chamou decide — o cascade de
traducao pula pro proximo provider, a capa cai na capa raspada.
"""

from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

import httpx
from google.genai import errors

from app.gemini_client import GEMINI_TIMEOUT_S, GeminiTimeoutError
from app.logging_conf import get_logger

log = get_logger("genai-retry")

T = TypeVar("T")

_RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}


async def call_with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    op: str = "genai_call",
    chapter: int | None = None,
) -> T:
    """Chama ``fn()`` com backoff exponencial em erros transitorios.

    Sleep: ``base_delay * 2^attempt`` clipado em ``max_delay``, com jitter
    aleatorio ±20% pra evitar thundering herd quando varios jobs sincronizam.
    """
    last_exc: errors.APIError | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except httpx.TimeoutException as exc:
            log.warning("genai_timeout", op=op, chapter=chapter, timeout_s=GEMINI_TIMEOUT_S)
            where = f" no cap {chapter}" if chapter is not None else ""
            raise GeminiTimeoutError(
                f"Gemini nao respondeu em {GEMINI_TIMEOUT_S}s ({op}{where})"
            ) from exc
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            is_retryable = code in _RETRYABLE_CODES
            if not is_retryable or attempt >= max_attempts - 1:
                if is_retryable:
                    log.warning(
                        "genai_retry_exhausted",
                        op=op, chapter=chapter, attempts=attempt + 1,
                        code=code, status=status,
                    )
                raise
            last_exc = exc
            sleep_s = min(base_delay * (2 ** attempt), max_delay)
            sleep_s *= 0.8 + random.random() * 0.4
            log.warning(
                "genai_retrying",
                op=op, chapter=chapter, attempt=attempt + 1,
                next_in_s=round(sleep_s, 1), code=code, status=status,
                message=str(getattr(exc, "message", exc))[:140],
            )
            await asyncio.sleep(sleep_s)
    # Inalcancavel (loop sempre retorna ou levanta), mas defensivo
    assert last_exc is not None
    raise last_exc
