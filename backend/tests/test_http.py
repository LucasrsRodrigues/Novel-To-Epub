"""HttpClient: politica de retry e deteccao de desafio anti-bot."""

import asyncio

import httpx
import pytest

from app.scraper.errors import BlockedError, FetchError
from app.scraper.http import HttpClient

CF = {"server": "cloudflare"}


def _run(status, headers, body):
    hits = 0

    def handler(request):
        nonlocal hits
        hits += 1
        return httpx.Response(status, headers=headers, text=body)

    async def main():
        c = HttpClient(min_delay=0, max_delay=0, max_retries=1)
        c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await c.get_text("https://site.x/p", throttle=False)
        finally:
            await c._client.aclose()

    with pytest.raises(FetchError) as info:
        asyncio.run(main())
    return info.value, hits


@pytest.mark.parametrize(
    "status,headers,body",
    [
        (403, CF, "<html>Forbidden</html>"),  # hotlink comum atras do Cloudflare
        (404, {}, "not found"),
    ],
)
def test_plain_errors_are_fetch_errors_without_retry(status, headers, body):
    err, hits = _run(status, headers, body)
    assert type(err) is FetchError and err.status == status and hits == 1


def test_origin_503_behind_cloudflare_is_retried():
    err, hits = _run(503, CF, "<html>Service Unavailable</html>")
    assert type(err) is FetchError and hits == 2


@pytest.mark.parametrize(
    "status,headers,body",
    [
        (503, CF, "<html><head><title>Just a moment...</title>"),
        (403, CF, '<script src="/cdn-cgi/challenge-platform/h/b"></script>'),
        (403, {"cf-mitigated": "challenge"}, ""),
        (403, {"server": "ddos-guard"}, "<title>DDoS-Guard</title>"),
    ],
)
def test_challenges_are_blocked_errors_without_retry(status, headers, body):
    err, hits = _run(status, headers, body)
    assert isinstance(err, BlockedError) and err.status == status and hits == 1


def test_429_waits_what_retry_after_asks(monkeypatch):
    """O backoff fixo (1s, 2s...) e trocado pelo tempo pedido pelo site."""
    import app.scraper.http as http_mod

    waits = []
    monkeypatch.setattr(http_mod, "_RETRY_AFTER_MAX_S", 60.0)
    original = http_mod._wait

    def spy(rs):
        w = original(rs)
        waits.append(w)
        return 0  # nao dorme de verdade no teste

    monkeypatch.setattr(http_mod, "_wait", spy)
    replies = iter([
        httpx.Response(429, headers={"retry-after": "7"}),
        httpx.Response(429, headers={"retry-after": "9999"}),  # absurdo → teto
        httpx.Response(200, text="ok"),
    ])

    async def main():
        c = HttpClient(min_delay=0, max_delay=0, max_retries=3)
        c._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: next(replies)))
        try:
            return await c.get_text("https://site.x/p", throttle=False)
        finally:
            await c._client.aclose()

    assert asyncio.run(main()) == "ok"
    assert waits == [7.0, 60.0]


def test_retry_after_http_date():
    from email.utils import format_datetime
    from datetime import datetime, timedelta, timezone

    from app.scraper.http import _retry_after_s

    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    secs = _retry_after_s(httpx.Response(429, headers={"retry-after": when}))
    assert 25 <= secs <= 30
    assert _retry_after_s(httpx.Response(429)) is None
