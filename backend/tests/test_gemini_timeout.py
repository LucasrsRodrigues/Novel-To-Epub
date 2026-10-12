"""Chamada ao Gemini que nunca responde vira GeminiTimeoutError legivel."""

import asyncio

import pytest
from google import genai
from google.genai import types

import app.gemini_client as gc
import app.translation.retry as retry_mod
from app.translation.retry import call_with_retry


def test_shared_client_has_timeout():
    c = gc.make_genai_client(use_vertex=False, api_key="x")
    assert c._api_client._http_options.timeout == gc.GEMINI_TIMEOUT_S * 1000


def test_hanging_server_raises_readable_timeout(monkeypatch):
    monkeypatch.setattr(retry_mod, "GEMINI_TIMEOUT_S", 1)

    async def hang(reader, writer):
        await asyncio.sleep(3600)

    async def main():
        srv = await asyncio.start_server(hang, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        client = genai.Client(
            api_key="x",
            http_options=types.HttpOptions(base_url=f"http://127.0.0.1:{port}", timeout=1000),
        )
        try:
            await call_with_retry(
                lambda: client.aio.models.generate_content(model="m", contents="oi"),
                op="translate_chapter",
                chapter=7,
            )
        finally:
            srv.close()

    with pytest.raises(gc.GeminiTimeoutError, match=r"nao respondeu em 1s \(translate_chapter no cap 7\)"):
        asyncio.run(main())
