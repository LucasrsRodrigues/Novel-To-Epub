"""Cliente HTTP async com rate limit, User-Agent realista e retry.

Compartilhado por todos os adapters. O rate limit serializa os requests e
insere um delay aleatorio entre eles (1-3s por padrao) para ser educado com
os servidores.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.logging_conf import get_logger
from app.scraper.errors import BlockedError, FetchError

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

# Erros transitorios que valem a pena re-tentar. Um 403/404 nao melhora com
# backoff — re-tentar so queima tempo (e reforca o bloqueio), entao de HTTP so
# 408/425/429 e 5xx entram no retry (e nem esses, se forem desafio anti-bot).
_RETRYABLE_STATUS = {408, 425, 429}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # Desafio anti-bot (muitas vezes 503) nao passa com backoff — so atrasa
        # o erro e reforca o bloqueio.
        if _challenge_reason(exc.response):
            return False
        code = exc.response.status_code
        return code in _RETRYABLE_STATUS or code >= 500
    return False


# Marcas das paginas de desafio/bloqueio no corpo da resposta. O header
# ``server: cloudflare`` sozinho NAO serve: ele vem em TODA resposta de site
# atras do Cloudflare, entao um 403 comum (hotlink de capa, pagina proibida) ou
# um 503 real da origem seriam rotulados como anti-bot.
_CHALLENGE_MARKERS = {
    "Cloudflare": (
        "<title>just a moment",
        "/cdn-cgi/challenge-platform/",
        "cf-browser-verification",
        "attention required! | cloudflare",
    ),
    "DDoS-Guard": ("ddos-guard",),
}


def _challenge_reason(resp: httpx.Response) -> str | None:
    """Detecta um desafio anti-bot (Cloudflare & cia) na resposta."""
    if resp.headers.get("cf-mitigated") == "challenge":
        return "Cloudflare"
    if resp.status_code not in (403, 429, 503):
        return None
    server = resp.headers.get("server", "").lower()
    guard = (
        "Cloudflare" if "cloudflare" in server
        else "DDoS-Guard" if "ddos-guard" in server
        else None
    )
    if guard is None:
        return None
    try:
        body = resp.text[:20000].lower()
    except Exception:  # corpo nao decodificavel → sem como confirmar
        return None
    return guard if any(m in body for m in _CHALLENGE_MARKERS[guard]) else None


# Teto pra respeitar o Retry-After: o job e serial, entao dormir mais que isso
# seguraria a fila inteira — melhor falhar o capitulo (e cair pro mirror).
_RETRY_AFTER_MAX_S = 60.0
_backoff = wait_exponential(multiplier=1, min=1, max=10)


def _retry_after_s(resp: httpx.Response) -> float | None:
    """Segundos pedidos pelo header ``Retry-After`` (numero ou HTTP-date)."""
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        secs = float(raw)
    except ValueError:
        try:
            when = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        secs = (when - datetime.now(timezone.utc)).total_seconds()
    return min(_RETRY_AFTER_MAX_S, max(0.0, secs))


def _wait(retry_state: RetryCallState) -> float:
    """Backoff exponencial — ou o que o site pediu no Retry-After (429/503)."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, httpx.HTTPStatusError):
        asked = _retry_after_s(exc.response)
        if asked is not None:
            return asked
    return _backoff(retry_state)


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
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self.max_retries + 1),
            wait=_wait,
            reraise=True,
        )
        async def _do() -> httpx.Response:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return resp

        try:
            return await _do()
        except httpx.HTTPStatusError as exc:
            guard = _challenge_reason(exc.response)
            if guard:
                log.warning("fetch_blocked", url=url, guard=guard)
                raise BlockedError(
                    f"{urlsplit(url).netloc} esta protegido por {guard} e devolveu um "
                    f"desafio anti-bot (HTTP {exc.response.status_code}). O site nao "
                    f"pode ser capturado por HTTP direto — use outro mirror/fonte "
                    f"para esta obra.",
                    status=exc.response.status_code,
                ) from exc
            log.warning("fetch_failed", url=url, error=str(exc))
            raise FetchError(
                f"Falha ao baixar {url}: {exc}", status=exc.response.status_code
            ) from exc
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
