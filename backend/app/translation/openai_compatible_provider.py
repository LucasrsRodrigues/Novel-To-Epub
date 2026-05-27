"""Provider que fala spec OpenAI Chat Completions (Groq, OpenRouter, Cerebras, etc).

Por que UM provider cobre todos: Groq, OpenRouter, Cerebras, Together, DeepInfra,
DeepSeek (api.deepseek.com), Mistral, e o próprio OpenAI usam o mesmo formato de
request (`POST /v1/chat/completions` com `{model, messages, response_format}`).
Diferenças ficam só em (1) base_url, (2) catalog de modelos, (3) qual flag de
JSON funciona melhor.

JSON mode tem 2 sabores aceitos pelos providers — tentamos os 2:
  - `response_format: {"type": "json_schema", "json_schema": {...}}` (OpenAI strict)
  - `response_format: {"type": "json_object"}` (mais leniente, instruir schema no prompt)

Modelos open (Llama 3.3, Qwen 2.5, DeepSeek) variam — alguns ignoram strict mode.
Estratégia: tenta json_object (compatibilidade ampla) + instrução no prompt.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.logging_conf import get_logger
from app.translation.gemini_provider import (
    GeminiTranslationError,
    _GlossaryDelta,
    _TranslationOutput,
    _build_system_prompt,
)
from app.translation.glossary import GlossaryEntry
from app.translation.provider import TranslationProvider, TranslationResult

log = get_logger("openai-compat")


# Configs conhecidas dos providers populares — facilita usuario nao errar URL
PROVIDER_BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "together": "https://api.together.xyz/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "openai": "https://api.openai.com/v1",
}


# Codigos HTTP transitorios — cascade decide se retenta no mesmo provider ou pula.
# 413 (Request Too Large) entra aqui porque Groq usa 413 pra TPM-per-minute
# excedido — funciona normal após reset do minuto (mesmo padrão de 429).
RETRYABLE_HTTP = {408, 413, 429, 500, 502, 503, 504}


class OpenAICompatTranslationError(GeminiTranslationError):
    """Reuso da hierarquia pra UI tratar igual ao Gemini erro."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        # Retry-After header (em segundos) ou Reset header — provider diz EXATAMENTE
        # quando podemos tentar de novo. Cascade usa isso pra setar cooldown preciso.
        self.retry_after_s = retry_after_s


def _schema_instruction() -> str:
    """Bloco que entra no system prompt explicando o JSON esperado.

    Modelos open precisam ver isso explicito (response_format=json_object so
    garante que SAI JSON, nao garante que segue o schema).
    """
    return """
FORMATO DA SAÍDA (JSON ESTRITO):
Responda EXCLUSIVAMENTE com um JSON neste formato (sem markdown, sem comentários):

{
  "translated_title": "string — título traduzido",
  "translated_html": "string — HTML traduzido com mesma sequência de <p>",
  "new_glossary_entries": [
    {
      "term": "termo original em inglês",
      "canonical_pt": "forma em PT (igual ao term pra nomes próprios)",
      "kind": "character|place|ability|organization|system_term|other",
      "gender": "male|female|non-binary|unknown|n/a",
      "notes": "1 frase de contexto",
      "confidence": "high|medium|low"
    }
  ]
}

NÃO escreva nada antes ou depois do JSON. NÃO use blocos ```json.
"""


def _safe_json_parse(text: str) -> dict[str, Any] | None:
    """Parse defensivo — modelos open as vezes envolvem em ```json...``` ou prefacio."""
    text = text.strip()
    # Remove markdown fence se veio
    if text.startswith("```"):
        lines = text.split("\n")
        # tira primeira (```json) e ultima (```)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # Tenta achar o primeiro { até o último } (modelos as vezes adicionam preface)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class OpenAICompatibleProvider(TranslationProvider):
    """Generaliza Groq / OpenRouter / Cerebras / DeepSeek / Together / etc."""

    def __init__(
        self,
        *,
        provider_name: str,  # "groq" | "openrouter" | "cerebras" | ...
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.name = provider_name
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or PROVIDER_BASE_URLS.get(provider_name)
        if not self.base_url:
            raise ValueError(
                f"provider {provider_name!r} sem base_url conhecida — passe `base_url=`"
            )
        self.timeout = timeout

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
        system = _build_system_prompt(
            novel_title, target_language, glossary,
            style_profile_block=style_profile_block,
            style_anchor_block=style_anchor_block,
        ) + _schema_instruction()
        user_msg = f"TÍTULO DO CAPÍTULO: {chapter_title}\n\nHTML DO CAPÍTULO:\n{text_html}"

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter exige App identification (boa pratica em qualquer provider)
        if self.name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/local/novel-to-epub"
            headers["X-Title"] = "Novel to EPUB"

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            # json_object: ampla compat. strict json_schema falha em alguns providers/modelos
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }

        # 2 tentativas de PARSE (modelo as vezes ignora JSON em 1 try mas acerta na 2);
        # erros HTTP transitorios propagam pra cascade decidir.
        parsed_dict: dict[str, Any] | None = None
        content = ""
        usage: dict[str, int] = {}
        last_err: str | None = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(2):
                try:
                    resp = await client.post(url, headers=headers, json=body)
                except httpx.HTTPError as exc:
                    raise OpenAICompatTranslationError(
                        f"{self.name}: rede/timeout no cap {chapter_index}: {exc}",
                        status_code=None,
                    ) from exc

                if resp.status_code in RETRYABLE_HTTP:
                    # Propaga pro cascade — ele decide se tenta de novo ou pula provider
                    detail = _short_error_detail(resp)
                    retry_after = _parse_retry_after(resp)
                    raise OpenAICompatTranslationError(
                        f"{self.name} HTTP {resp.status_code} no cap {chapter_index}: {detail}",
                        status_code=resp.status_code,
                        retry_after_s=retry_after,
                    )
                if resp.status_code >= 400:
                    detail = _short_error_detail(resp)
                    raise OpenAICompatTranslationError(
                        f"{self.name} HTTP {resp.status_code} (permanente) no cap {chapter_index}: {detail}",
                        status_code=resp.status_code,
                    )

                payload = resp.json()
                choices = payload.get("choices") or []
                if not choices:
                    last_err = "resposta sem 'choices'"
                    continue
                content = choices[0].get("message", {}).get("content", "") or ""
                usage = payload.get("usage", {}) or {}
                parsed_dict = _safe_json_parse(content)
                if parsed_dict is not None:
                    break
                last_err = f"JSON inválido (attempt={attempt}, preview={content[:120]!r})"
                log.warning(
                    "openai_compat_parse_failed",
                    provider=self.name, chapter=chapter_index,
                    attempt=attempt, detail=last_err,
                )

        if parsed_dict is None:
            raise OpenAICompatTranslationError(
                f"{self.name}: JSON inválido após 2 tentativas no cap {chapter_index}: {last_err}"
            )

        try:
            parsed = _TranslationOutput.model_validate(parsed_dict)
        except ValidationError as exc:
            raise OpenAICompatTranslationError(
                f"{self.name}: schema inválido no cap {chapter_index}: {exc.errors()[:2]}"
            ) from exc

        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or 0)

        log.info(
            "openai_compat_translated",
            provider=self.name, model=self.model, chapter=chapter_index,
            glossary_in=len(glossary), new_entries=len(parsed.new_glossary_entries),
            input_tokens=input_tokens, output_tokens=output_tokens,
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
            input_tokens=input_tokens, output_tokens=output_tokens,
            model=f"{self.name}/{self.model}",
        )


def _parse_retry_after(resp: httpx.Response) -> float | None:
    """Lê quanto tempo até poder retentar. Múltiplos headers possíveis:
      - `Retry-After`: padrão HTTP, em segundos OU data HTTP-date
      - `x-ratelimit-reset-*`: Groq/OpenAI variant — segundos até reset

    Limita em 600s pra não dormir absurdo (se vier 3600 = 1h, melhor desistir
    desse provider e cair pro próximo).
    """
    ra = resp.headers.get("retry-after")
    if ra:
        try:
            return min(600.0, max(1.0, float(ra)))
        except ValueError:
            pass  # date format — ignora, usa default
    # Groq retorna "x-ratelimit-reset-requests" / "x-ratelimit-reset-tokens"
    for h in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        val = resp.headers.get(h)
        if val:
            try:
                # formato pode ser "12.34s" ou só número
                num = float(val.rstrip("s"))
                return min(600.0, max(1.0, num))
            except ValueError:
                continue
    return None


def _short_error_detail(resp: httpx.Response) -> str:
    """Extrai mensagem util do erro JSON (varia por provider)."""
    try:
        body = resp.json()
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)[:240]
            return str(body)[:240]
    except Exception:
        pass
    return resp.text[:240]
