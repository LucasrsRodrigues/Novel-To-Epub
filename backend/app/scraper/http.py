"""Cliente HTTP async com rate limit, User-Agent realista e retry.

Compartilhado por todos os adapters. O rate limit serializa os requests e
insere um delay aleatorio entre eles (1-3s por padrao) para ser educado com
os servidores.
"""

from __future__ import annotations

import asyncio
import random

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.logging_conf import get_logger
from app.scraper.errors import FetchError

log = get_logger("http")

DEFAULT_HEADERS = {
    "User-Agent": settings.user_agent,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Erros transitorios que valem a pena re-tentar.
_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class HttpClient:
    def __init__(
        self,
        *,
        min_delay: float | None = None,
        max_delay: float | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        self.min_delay = settings.min_delay if min_delay is None else min_delay
        self.max_delay = settings.max_delay if max_delay is None else max_delay
        self.max_retries = settings.max_retries if max_retries is None else max_retries
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=settings.request_timeout if timeout is None else timeout,
            follow_redirects=True,
        )
        # serializa os requests para respeitar o rate limit
        self._lock = asyncio.Lock()

    async def _throttle(self) -> None:
        async with self._lock:
            await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

    async def _request(self, url: str) -> httpx.Response:
        @retry(
            retry=retry_if_exception_type(_RETRYABLE),
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )
        async def _do() -> httpx.Response:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return resp

        try:
            return await _do()
        except httpx.HTTPError as exc:
            log.warning("fetch_failed", url=url, error=str(exc))
            raise FetchError(f"Falha ao baixar {url}: {exc}") from exc

    async def get_text(self, url: str, *, throttle: bool = True) -> str:
        # ``throttle=False`` pula o rate-limit global (lock + sleep). Uso esperado:
        # paginacao de TOC (endpoints SSR baratos do mesmo backend) onde o adapter
        # quer paralelizar via gather/semaforo. NUNCA usar pra fetch_chapter, que
        # eh o caminho quente sujeito a anti-bot.
        if throttle:
            await self._throttle()
        log.debug("GET", url=url, throttle=throttle)
        resp = await self._request(url)
        return resp.text

    async def get_bytes(self, url: str, *, throttle: bool = True) -> bytes:
        if throttle:
            await self._throttle()
        log.debug("GET (bytes)", url=url, throttle=throttle)
        resp = await self._request(url)
        return resp.content

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "HttpClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()
