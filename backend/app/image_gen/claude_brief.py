"""Brief visual da capa (cena + estilo) escrito pelo Claude.

So o TEXTO do brief: a imagem continua sendo gerada pelo modelo de imagem do
Gemini (o Claude nao gera imagem). Ativado por ``cover_brief_provider =
"claude"`` nas configuracoes; o cover_generator cai pro Gemini se esta funcao
levantar (sem chave, recusa, erro de rede) — a capa nunca deixa de sair.
"""

from __future__ import annotations

import json

import anthropic

from app.logging_conf import get_logger
from app.translation.claude_provider import (
    DEFAULT_MODEL,
    _FALLBACK_BETA,
    _MODELS_WITH_FALLBACK,
)

log = get_logger("claude_brief")

_SCHEMA = {
    "type": "object",
    "properties": {
        "scene": {"type": "string"},
        "style": {"type": "string"},
    },
    "required": ["scene", "style"],
    "additionalProperties": False,
}


class ClaudeBriefError(RuntimeError):
    """O Claude nao produziu um brief utilizavel (o chamador cai pro Gemini)."""


async def build_brief_with_claude(
    *, api_key: str, model: str | None, system: str, user_prompt: str
) -> tuple[dict, str, int, int]:
    """Devolve ``({"scene", "style"}, modelo_que_respondeu, input_tokens, output_tokens)``."""
    model = model or DEFAULT_MODEL
    extra: dict = {}
    if model in _MODELS_WITH_FALLBACK:
        extra = {"betas": [_FALLBACK_BETA], "fallbacks": "default"}
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0, max_retries=1)
    try:
        msg = await client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
            **extra,
        )
    except anthropic.APIError as exc:
        raise ClaudeBriefError(f"Claude falhou no brief da capa: {str(exc)[:200]}") from exc
    finally:
        await client.close()

    if msg.stop_reason == "refusal":
        raise ClaudeBriefError("Claude recusou o brief da capa (safety)")
    text = next((b.text for b in msg.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        scene, style = str(data["scene"]).strip(), str(data["style"]).strip()
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ClaudeBriefError(f"brief do Claude fora do formato: {text[:120]!r}") from exc
    if not scene or not style:
        raise ClaudeBriefError("brief do Claude veio vazio")

    u = msg.usage
    input_tokens = (
        (u.input_tokens or 0)
        + (getattr(u, "cache_read_input_tokens", 0) or 0)
        + (getattr(u, "cache_creation_input_tokens", 0) or 0)
    )
    log.info("claude_brief_built", model=msg.model, scene=scene[:120], style=style[:60])
    return {"scene": scene, "style": style}, msg.model, input_tokens, u.output_tokens or 0
