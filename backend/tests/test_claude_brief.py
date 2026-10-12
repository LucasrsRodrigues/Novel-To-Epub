"""Brief da capa pelo Claude (texto) com fallback pro Gemini."""

import asyncio
import json
from types import SimpleNamespace

import pytest

import app.image_gen.claude_brief as cb
import app.image_gen.cover_generator as cg
from app.db.settings_store import SettingsStore


@pytest.fixture(autouse=True)
def no_env_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_gemini_is_default_provider():
    assert asyncio.run(cg._try_claude_brief("prompt", 1)) is None


def test_claude_selected_without_key_falls_back():
    SettingsStore().update({"cover_brief_provider": "claude"})
    assert asyncio.run(cg._try_claude_brief("prompt", 1)) is None


def test_claude_brief_used_and_usage_recorded(monkeypatch):
    SettingsStore().update({"cover_brief_provider": "claude", "claude_api_key": "sk-test"})
    seen = {}

    async def fake(*, api_key, model, system, user_prompt):
        seen.update(api_key=api_key, system=system, user_prompt=user_prompt)
        return {"scene": "Um mago sob relâmpagos", "style": "dark fantasy"}, "claude-opus-5-5", 800, 120

    monkeypatch.setattr(cb, "build_brief_with_claude", fake)
    from app.db.cache import ChapterCache
    from app.models import NovelMeta

    nid = ChapterCache().upsert_novel("x", "n", NovelMeta(title="N", source_url="u", chapters=[]))
    brief = asyncio.run(cg._try_claude_brief("PROMPT DO VOLUME", nid))
    assert (brief.scene, brief.style) == ("Um mago sob relâmpagos", "dark fantasy")
    assert seen["api_key"] == "sk-test" and seen["system"] == cg._BRIEF_SYSTEM
    assert seen["user_prompt"] == "PROMPT DO VOLUME"
    from app.db import models as orm
    from app.db.database import get_session

    with get_session() as s:
        row = s.query(orm.GeminiUsage).filter_by(op="cover_brief").one()
    assert row.model == "claude/claude-opus-5-5" and row.cost_usd > 0  # preço do Claude aplicado


def test_claude_error_falls_back_to_gemini(monkeypatch):
    SettingsStore().update({"cover_brief_provider": "claude", "claude_api_key": "sk-test"})

    async def boom(**kw):
        raise cb.ClaudeBriefError("recusou")

    monkeypatch.setattr(cb, "build_brief_with_claude", boom)
    assert asyncio.run(cg._try_claude_brief("p", 1)) is None


class _FakeMessages:
    def __init__(self, reply):
        self.reply, self.kw = reply, None

    async def create(self, **kw):
        self.kw = kw
        return self.reply


class _FakeClient:
    last = None

    def __init__(self, reply):
        self.beta = SimpleNamespace(messages=_FakeMessages(reply))
        _FakeClient.last = self

    async def close(self):
        pass


def _reply(stop="end_turn", text=json.dumps({"scene": "S", "style": "T"}), model="claude-opus-5-5"):
    return SimpleNamespace(
        stop_reason=stop, model=model, content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


def _patch_client(monkeypatch, reply):
    monkeypatch.setattr(cb.anthropic, "AsyncAnthropic", lambda **kw: _FakeClient(reply))


def test_request_has_schema_and_server_fallback(monkeypatch):
    _patch_client(monkeypatch, _reply())
    data, model, i, o = asyncio.run(cb.build_brief_with_claude(
        api_key="k", model=None, system="SYS", user_prompt="U"))
    kw = _FakeClient.last.beta.messages.kw
    assert data == {"scene": "S", "style": "T"} and model == "claude-opus-5-5" and (i, o) == (10, 5)
    assert kw["model"] == "claude-opus-5-5" and kw["system"] == "SYS"
    assert kw["output_config"]["format"]["schema"]["required"] == ["scene", "style"]
    assert kw["fallbacks"] == "default"


def test_haiku_brief_without_fallback_and_refusal_raises(monkeypatch):
    _patch_client(monkeypatch, _reply(model="claude-haiku-5-5"))
    asyncio.run(cb.build_brief_with_claude(api_key="k", model="claude-haiku-5-5", system="S", user_prompt="U"))
    assert "fallbacks" not in _FakeClient.last.beta.messages.kw
    _patch_client(monkeypatch, _reply(stop="refusal", text=""))
    with pytest.raises(cb.ClaudeBriefError, match="recusou"):
        asyncio.run(cb.build_brief_with_claude(api_key="k", model=None, system="S", user_prompt="U"))


def test_settings_round_trip_and_validation():
    from starlette.testclient import TestClient

    from app.api.server import create_app

    with TestClient(create_app()) as c:
        assert c.get("/api/settings").json()["cover_brief_provider"] == "gemini"
        assert c.put("/api/settings", json={"cover_brief_provider": "claude"}).status_code == 200
        assert c.get("/api/settings").json()["cover_brief_provider"] == "claude"
        assert c.put("/api/settings", json={"cover_brief_provider": "dall-e"}).status_code == 422
