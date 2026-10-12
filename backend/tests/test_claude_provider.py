"""ClaudeProvider com o SDK simulado (sem rede)."""

import asyncio
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.translation.claude_provider import ClaudeProvider, ClaudeTranslationError
from app.translation.gemini_provider import GeminiContentBlockedError
from app.translation.glossary import GlossaryEntry

OUT = {
    "translated_title": "Capítulo 1",
    "translated_html": "<p>Olá, Sunny.</p>",
    "new_glossary_entries": [
        {"term": "Nephis", "canonical_pt": "Nephis", "kind": "character",
         "gender": "female", "notes": "aliada", "confidence": "high"}
    ],
}


def _msg(stop_reason="end_turn", text=json.dumps(OUT), model="claude-opus-5-5"):
    usage = SimpleNamespace(input_tokens=900, output_tokens=700,
                            cache_read_input_tokens=1500, cache_creation_input_tokens=0)
    return SimpleNamespace(stop_reason=stop_reason, stop_details=SimpleNamespace(category="general_harms"),
                           content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
                           usage=usage, model=model)


class _Stream:
    def __init__(self, result):
        self.result = result

    async def __aenter__(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self

    async def __aexit__(self, *a):
        return False

    async def get_final_message(self):
        return self.result


def _provider(result, model="claude-opus-5-5"):
    p = ClaudeProvider(api_key="test", model=model)
    calls = []

    def fake_stream(**kw):
        calls.append(kw)
        return _Stream(result)

    p.client.beta.messages.stream = fake_stream
    return p, calls


def _run(p):
    gl = [GlossaryEntry(term="Sunny", canonical_pt="Sunny", kind="character", gender="male")]
    return asyncio.run(p.translate_chapter(
        text_html="<p>Hello, Sunny.</p>", chapter_title="Chapter 1", target_language="pt-BR",
        glossary=gl, novel_title="Shadow Slave", chapter_index=1,
        style_anchor_block="\nANCORA",
    ))


def test_success_parses_output_and_counts_cached_input():
    p, calls = _provider(_msg())
    r = _run(p)
    assert r.translated_html == "<p>Olá, Sunny.</p>" and r.translated_title == "Capítulo 1"
    assert [e.term for e in r.new_entries] == ["Nephis"] and r.new_entries[0].gender == "female"
    assert r.input_tokens == 900 + 1500 and r.output_tokens == 700
    assert r.model == "claude/claude-opus-5-5"


def test_request_shape_cache_on_static_rules_glossary_after_breakpoint():
    p, calls = _provider(_msg())
    _run(p)
    kw = calls[0]
    static, dynamic = kw["system"]
    assert static["cache_control"] == {"type": "ephemeral"} and "cache_control" not in dynamic
    assert "REGRA FUNDAMENTAL" in static["text"] and "Sunny" not in static["text"]
    assert "NOVEL: Shadow Slave" in dynamic["text"] and "Sunny" in dynamic["text"] and "ANCORA" in dynamic["text"]
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["effort"] == "medium"
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in kw  # Opus 5.5: adaptativo sempre ligado


def test_static_block_is_identical_across_chapters_and_novels():
    p, calls = _provider(_msg())
    _run(p)
    asyncio.run(p.translate_chapter(text_html="<p>x</p>", chapter_title="Ch 2", target_language="pt-BR",
                                    glossary=[], novel_title="Outra Novel", chapter_index=2))
    assert calls[0]["system"][0] == calls[1]["system"][0]  # prefixo cacheavel estavel


def test_haiku_has_no_server_fallback():
    p, calls = _provider(_msg(model="claude-haiku-5-5"), model="claude-haiku-5-5")
    _run(p)
    assert "fallbacks" not in calls[0] and "betas" not in calls[0]


def test_refusal_becomes_content_block_error():
    p, _ = _provider(_msg(stop_reason="refusal", text=""))
    with pytest.raises(GeminiContentBlockedError, match="safety"):
        _run(p)


def test_truncated_output_is_error():
    p, _ = _provider(_msg(stop_reason="max_tokens", text='{"translated_title": "x'))
    with pytest.raises(ClaudeTranslationError, match="max_tokens"):
        _run(p)


def test_rate_limit_carries_status_and_retry_after():
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(429, headers={"retry-after": "42"}, request=req)
    p, _ = _provider(anthropic.RateLimitError("slow down", response=resp, body=None))
    with pytest.raises(ClaudeTranslationError) as info:
        _run(p)
    assert info.value.status_code == 429 and info.value.retry_after_s == 42.0


def test_overloaded_maps_to_5xx_status():
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(529, request=req)
    p, _ = _provider(anthropic.OverloadedError("overloaded", response=resp, body=None))
    with pytest.raises(ClaudeTranslationError) as info:
        _run(p)
    assert info.value.status_code == 529


def test_factory_builds_claude_from_settings_and_appends_to_order():
    from app.db.settings_store import SettingsStore
    from app.translation.factory import build_translator

    SettingsStore().update({"claude_api_key": "sk-test", "claude_model": "claude-sonnet-5-5",
                            "cascade_order": "gemini,groq"})
    t = build_translator("pt-BR")
    providers = t.provider.states if hasattr(t.provider, "states") else t.provider._states
    names = [s.provider.name for s in providers]
    assert names[-1] == "claude"
    claude = providers[-1].provider
    assert claude.model == "claude-sonnet-5-5"
