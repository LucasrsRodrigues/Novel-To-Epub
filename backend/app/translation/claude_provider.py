"""Provider de traducao via Claude (API da Anthropic, SDK oficial ``anthropic``).

Mesmo contrato dos outros providers (TranslationProvider): recebe o capitulo +
glossario selecionado + blocos de estilo e devolve HTML traduzido, titulo e
termos novos do glossario. Diferencas que importam:

- **Saida estruturada de verdade**: ``output_config.format`` com JSON Schema
  estrito — a resposta e garantidamente um JSON valido no formato pedido (sem
  as 2 tentativas de parse dos providers OpenAI-compatible).
- **Prompt caching**: o system prompt vai em 2 blocos. O 1º (regras fixas de
  traducao, ~1,5k tokens) leva ``cache_control`` e e reaproveitado entre
  capitulos — leitura do cache custa ~10% do input normal. O 2º (novel +
  glossario do capitulo + estilo) muda a cada capitulo e fica depois do
  breakpoint.
- **Streaming**: capitulo traduzido + termos novos pode passar de 10k tokens de
  saida; o SDK recomenda stream pra saidas longas (evita timeout HTTP). So
  usamos a mensagem final (``get_final_message``).
- **Recusa de conteudo**: web novel tem violencia; o classificador pode recusar
  (``stop_reason == "refusal"``). Com ``fallbacks="default"`` o proprio servidor
  re-tenta no modelo recomendado pra categoria. Se ainda assim recusar, vira
  ``GeminiContentBlockedError`` — o cascade tenta o proximo provider sem por o
  Claude em cooldown (nao e problema de saude do provider).
- **Rate limit / sobrecarga**: o SDK re-tenta 1x sozinho (429/529/5xx); se
  persistir, sobe ``ClaudeTranslationError`` com o status e o ``retry-after``
  — o cascade poe o Claude em cooldown exatamente por esse tempo.
"""

from __future__ import annotations

import json

import anthropic
from pydantic import ValidationError

from app.logging_conf import get_logger
from app.translation.gemini_provider import (
    GeminiContentBlockedError,
    _NEW_TERMS_AND_HTML,
    _RULES,
    _TranslationOutput,
    _glossary_section,
    _intro,
)
from app.translation.glossary import GlossaryEntry
from app.translation.openai_compatible_provider import OpenAICompatTranslationError
from app.translation.provider import TranslationProvider, TranslationResult

log = get_logger("claude_provider")

DEFAULT_MODEL = "claude-opus-5-5"

# Recusa → o servidor re-tenta no modelo recomendado pra categoria da recusa.
# Nao existe pro Haiku (la uma recusa continua recusa — nao mandamos o campo).
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_MODELS_WITH_FALLBACK = ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")

# Teto por chamada (stream inteiro). Capitulo longo + glossario + raciocinio
# adaptativo cabe com folga; acima disso o cascade segue pro proximo provider.
_TIMEOUT_S = 300.0
_MAX_TOKENS = 32000

# JSON Schema estrito da resposta (espelha _TranslationOutput/_GlossaryDelta).
_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "translated_title": {"type": "string"},
        "translated_html": {"type": "string"},
        "new_glossary_entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "canonical_pt": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "character", "place", "ability",
                            "organization", "system_term", "other",
                        ],
                    },
                    "gender": {
                        "type": "string",
                        "enum": ["male", "female", "non-binary", "unknown", "n/a"],
                    },
                    "notes": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["term", "canonical_pt", "kind", "gender", "notes", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["translated_title", "translated_html", "new_glossary_entries"],
    "additionalProperties": False,
}


class ClaudeTranslationError(OpenAICompatTranslationError):
    """Falha do Claude com status/retry-after — o cascade trata como os demais
    providers HTTP (429 → cooldown pelo retry-after, 5xx/529 → cooldown curto)."""


def _static_system(target_language: str) -> str:
    """Regras fixas — identicas entre capitulos (e novels), por isso cacheaveis."""
    return (
        f"{_intro(target_language)}\n\n"
        f"{_RULES}\n\n"
        f"{_NEW_TERMS_AND_HTML.format(where='abaixo')}"
    )


def _dynamic_system(
    novel_title: str,
    glossary: list[GlossaryEntry],
    style_profile_block: str,
    style_anchor_block: str,
) -> str:
    """Parte que muda por capitulo — vai DEPOIS do breakpoint do cache."""
    return (
        f"NOVEL: {novel_title}\n\n"
        f"{_glossary_section(glossary)}\n"
        f"{style_profile_block}{style_anchor_block}"
    )


def _retry_after_s(exc: anthropic.APIStatusError) -> float | None:
    raw = exc.response.headers.get("retry-after") if exc.response is not None else None
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


class ClaudeProvider(TranslationProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, *, effort: str = "medium"):
        self.model = model
        self.effort = effort
        # 1 retry no SDK (backoff dele, respeita retry-after) pra soluco
        # passageiro; insistencia alem disso e com o cascade.
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=_TIMEOUT_S, max_retries=1
        )

    async def translate_chapter(
        self,
        *,
        text_html: str,
        chapter_title: str,
        target_language: str,
        glossary: list[GlossaryEntry],
        novel_title: str,
        novel_slug: str | None = None,
        chapter_index: int | None = None,
        style_profile_block: str = "",
        style_anchor_block: str = "",
    ) -> TranslationResult:
        system = [
            {
                "type": "text",
                "text": _static_system(target_language),
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": _dynamic_system(
                    novel_title, glossary, style_profile_block, style_anchor_block
                ),
            },
        ]
        user_msg = f"TÍTULO DO CAPÍTULO: {chapter_title}\n\nHTML DO CAPÍTULO:\n{text_html}"
        extra: dict = {}
        if self.model in _MODELS_WITH_FALLBACK:
            extra = {"betas": [_FALLBACK_BETA], "fallbacks": "default"}

        try:
            async with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
                },
                **extra,
            ) as stream:
                msg = await stream.get_final_message()
        except anthropic.RateLimitError as exc:
            raise ClaudeTranslationError(
                f"claude: rate limit (429) no cap {chapter_index}",
                status_code=429, retry_after_s=_retry_after_s(exc),
            ) from exc
        except anthropic.APIStatusError as exc:
            # 529 overloaded, 5xx, e tambem 4xx permanentes (chave invalida,
            # sem credito) — o cascade so poe cooldown em 429/5xx.
            raise ClaudeTranslationError(
                f"claude: HTTP {exc.status_code} ({getattr(exc, 'type', None) or 'erro'}) "
                f"no cap {chapter_index}: {str(exc)[:200]}",
                status_code=exc.status_code, retry_after_s=_retry_after_s(exc),
            ) from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            raise ClaudeTranslationError(
                f"claude: rede/timeout no cap {chapter_index}: {exc}", status_code=None
            ) from exc

        if msg.stop_reason == "refusal":
            category = getattr(getattr(msg, "stop_details", None), "category", None)
            # "safety" na mensagem: a UI (classifyFailure) rotula como edicao manual.
            raise GeminiContentBlockedError(
                f"Claude recusou o cap {chapter_index} (safety, categoria={category or '?'}). "
                f"Conteudo precisa de edicao manual."
            )
        if msg.stop_reason == "max_tokens":
            raise ClaudeTranslationError(
                f"claude: saida cortada em max_tokens ({_MAX_TOKENS}) no cap {chapter_index}"
            )

        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            parsed = _TranslationOutput.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ClaudeTranslationError(
                f"claude: JSON fora do schema no cap {chapter_index}: {str(exc)[:200]}"
            ) from exc

        u = msg.usage
        cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
        input_tokens = (u.input_tokens or 0) + cache_read + cache_write
        output_tokens = u.output_tokens or 0
        log.info(
            "claude_translated",
            model=msg.model, chapter=chapter_index, glossary_in=len(glossary),
            new_entries=len(parsed.new_glossary_entries),
            input_tokens=input_tokens, cache_read=cache_read, cache_write=cache_write,
            output_tokens=output_tokens, request_id=getattr(msg, "_request_id", None),
        )

        return TranslationResult(
            translated_html=parsed.translated_html,
            translated_title=parsed.translated_title,
            new_entries=[
                GlossaryEntry(
                    term=d.term, canonical_pt=d.canonical_pt, kind=d.kind,
                    gender=d.gender, notes=d.notes, confidence=d.confidence,
                    first_seen_chapter=chapter_index, source="llm",
                )
                for d in parsed.new_glossary_entries
            ],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            # msg.model = quem respondeu de fato (pode ser o fallback do servidor)
            model=f"claude/{msg.model}",
        )
