"""Provider de traducao usando Google Gemini (google-genai SDK).

Estrategia:
  - System prompt contem o glossario formatado + diretrizes de estilo.
  - O capitulo eh enviado como user message.
  - Saida ESTRUTURADA via response_schema (Pydantic): ``translated_html`` +
    ``new_glossary_entries[]`` numa unica chamada. Evita parsing fragil.
  - temperature=0.3 (deixa um pouco de estilo, mas previsivel).
"""

from __future__ import annotations

import asyncio
from typing import Literal

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field

from app.logging_conf import get_logger
from app.translation.glossary import GlossaryEntry
from app.translation.provider import TranslationProvider, TranslationResult
from app.translation.retry import call_with_retry

log = get_logger("gemini")


class GeminiTranslationError(RuntimeError):
    """O Gemini nao devolveu output utilizavel (safety, json, etc)."""


_LANG_NAMES = {
    "pt-BR": "português brasileiro",
    "pt-PT": "português europeu",
    "es": "espanhol",
    "fr": "francês",
}


class _GlossaryDelta(BaseModel):
    term: str = Field(description="termo original em inglês como aparece no texto")
    canonical_pt: str = Field(
        description=(
            "forma canônica em PT. Para personagens, habilidades, lugares e organizações "
            "DEVE SER IGUAL ao term (preservar em inglês). Só traduza para substantivos comuns."
        )
    )
    kind: Literal["character", "place", "ability", "organization", "system_term", "other"]
    gender: Literal["male", "female", "non-binary", "unknown", "n/a"]
    notes: str = Field(default="", description="contexto curto: papel/descrição (1 frase)")
    confidence: Literal["high", "medium", "low"] = Field(
        description="quão certo você está; low se inferiu por contexto ambíguo"
    )


class _TranslationOutput(BaseModel):
    translated_title: str = Field(description="título do capítulo traduzido")
    translated_html: str = Field(
        description="HTML traduzido preservando exatamente a estrutura de tags <p> do original"
    )
    new_glossary_entries: list[_GlossaryDelta] = Field(
        default_factory=list,
        description="termos novos (não no glossário fornecido) encontrados neste capítulo",
    )


def _format_glossary(entries: list[GlossaryEntry], *, max_chars: int = 8000) -> str:
    """Formata glossário pra prompt, com truncamento estratégico se passar do orçamento.

    `max_chars` evita estourar TPM de provider free (Groq free = 12k tokens
    por minuto, ~48k chars; nosso budget de 8k chars deixa folga pro
    capítulo + style anchor + schema). Quando precisar cortar:
      - Notes são truncadas pra 60 chars (info menos crítica que term/gender).
      - Prioridade de retenção: character > place > ability > organization > system_term > other.
      - Entries que sobram são descartadas com aviso.
    """
    if not entries:
        return "(vazio — adicione TODOS os nomes próprios e termos do mundo encontrados a new_glossary_entries)"

    # Ordena por prioridade pra priorizar character/place no truncate
    _PRIORITY = {"character": 0, "place": 1, "ability": 2, "organization": 3, "system_term": 4, "other": 5}
    ordered = sorted(entries, key=lambda e: (_PRIORITY.get(e.kind, 99), e.term.lower()))

    def _fmt(e: GlossaryEntry, notes_max: int) -> str:
        bits = [e.kind]
        if e.gender not in ("n/a", "unknown"):
            bits.append(e.gender)
        if e.notes:
            note = e.notes[:notes_max] + ("…" if len(e.notes) > notes_max else "")
            bits.append(note)
        return f'- {e.term} → "{e.canonical_pt}" ({", ".join(bits)})'

    # 1ª passada: notes inteiras
    lines = [_fmt(e, notes_max=240) for e in ordered]
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text

    # 2ª passada: trunca notes pra 60 chars
    lines = [_fmt(e, notes_max=60) for e in ordered]
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text

    # 3ª passada: corta entries do tail (menor prioridade) até caber
    kept: list[str] = []
    running = 0
    for ln in lines:
        if running + len(ln) + 1 > max_chars:
            break
        kept.append(ln)
        running += len(ln) + 1
    dropped = len(ordered) - len(kept)
    text = "\n".join(kept)
    if dropped > 0:
        text += f"\n(… {dropped} entries omitidas por limite de tokens — priorizei characters/places.)"
    return text


def _build_system_prompt(
    novel_title: str,
    target_language: str,
    glossary: list[GlossaryEntry],
    *,
    style_profile_block: str = "",
    style_anchor_block: str = "",
) -> str:
    """Monta o system prompt do tradutor.

    `style_profile_block` e `style_anchor_block` são opcionais — quando o
    volume tem um perfil/ancora salvos, são injetados pra forçar consistência
    de voz quando trocamos de provider/modelo no cascade.
    """
    lang = _LANG_NAMES.get(target_language, target_language)
    return f"""Você é um tradutor profissional de web novels do inglês para {lang}.

NOVEL: {novel_title}

REGRA FUNDAMENTAL — O QUE **NÃO** TRADUZIR (preservar EM INGLÊS, sem aportuguesar):
- Personagens: "Quinn", "Layla", "Voldemort", "Mei Lin"
- Habilidades/skills/poderes nomeados: "Fireball", "Sword Mastery", "Vampire's Bite", "Path of Glory"
- Cidades/lugares/regiões: "Hellpike", "Astoria", "the Mire", "Aldridge City"
- Organizações/facções/guildas: "Adventurer's Guild", "Phantom Force", "House Targaryen"
- Sistemas/itens nomeados: "Vampire System", "Excalibur", "Crimson Crown"

→ Para esses, no campo `new_glossary_entries`, `canonical_pt` **deve ser IGUAL** ao `term` original.
→ NUNCA invente uma tradução (não vire "Quinn" em "Quim", nem "Adventurer's Guild" em "Guilda dos Aventureiros").

O QUE **TRADUZIR** normalmente:
- Substantivos comuns: "the city" → "a cidade", "his sword" → "sua espada", "the guild" (genérico) → "a guilda"
- Verbos, adjetivos, ações, descrições
- Conteúdo narrativo de mensagens de sistema (mas preserve os nomes próprios dentro):
  "<You have learned Fireball>" → "<Você aprendeu Fireball>"
  "<Health Points: 80/100>" → "<Pontos de Vida: 80/100>"

ESTILO:
- Mantenha o tom narrativo e ritmo do original; prosa fluente, não literal palavra-por-palavra.
- Diálogos: use travessão (—) no início de cada fala (norma brasileira).
- Use gênero gramatical EXATAMENTE como indicado no glossário (male/female). Se Quinn é male, todas as referências em PT são masculinas: "ele", "cansado", "o jovem".

GLOSSÁRIO (use estes termos exatos para consistência através dos capítulos):
{_format_glossary(glossary)}

NOVOS TERMOS:
Adicione ao campo `new_glossary_entries` TODO nome próprio (qualquer coisa com inicial maiúscula que se refira a uma pessoa, lugar, habilidade, organização ou item nomeado) que NÃO está no glossário acima:
- Para personagens: infira `gender` do contexto (pronomes "he/she/they", descrições); confidence="low" se ambíguo.
- Para coisas (place/ability/organization/system_term): `gender="n/a"`.
- `canonical_pt` = `term` (mantém em inglês, lembra da regra fundamental).
- `notes`: 1 frase curta sobre o papel/contexto.

ESTRUTURA HTML:
A entrada vem como sequência de tags <p>...</p>. Sua saída `translated_html` deve ter EXATAMENTE o mesmo número de <p>, na mesma ordem. Não invente nem funda parágrafos.
{style_profile_block}{style_anchor_block}"""


class GeminiProvider(TranslationProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

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
        )
        user_msg = f"TÍTULO DO CAPÍTULO: {chapter_title}\n\nHTML DO CAPÍTULO:\n{text_html}"

        # Safety settings: por padrao o Gemini usa BLOCK_MEDIUM_AND_ABOVE em
        # todas as categorias, o que pega borda demais pra web novel (violencia
        # de combate, sangue, romance leve). BLOCK_NONE desliga o filtro
        # configuravel — o modelo ainda tem hard guardrails internos que nao
        # podem ser desativados (criancas, etc), mas o resto passa.
        # CIVIC_INTEGRITY (politica/eleicoes) e JAILBREAK nao sao mexidos.
        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=_TranslationOutput,
            temperature=0.3,
            safety_settings=safety_settings,
        )

        # Dois niveis de retry:
        #   1. call_with_retry: trata erros 5xx/429 (UNAVAILABLE, RESOURCE_EXHAUSTED,
        #      INTERNAL) com backoff exponencial.
        #   2. Loop manual (2 tentativas): trata `parsed=None` (safety filter
        #      bateu, JSON invalido, etc) — esses nao levantam exception, retornam
        #      response vazia.
        parsed: _TranslationOutput | None = None
        resp = None
        last_err: str | None = None
        for attempt in range(2):
            try:
                resp = await call_with_retry(
                    lambda: self.client.aio.models.generate_content(
                        model=self.model, contents=user_msg, config=config
                    ),
                    op="translate_chapter",
                    chapter=chapter_index,
                )
            except genai_errors.APIError as exc:
                # Esgotou retries transitorios OU erro permanente (4xx).
                code = getattr(exc, "code", "?")
                status = getattr(exc, "status", "?")
                msg = getattr(exc, "message", str(exc))
                raise GeminiTranslationError(
                    f"Gemini API error (code={code} status={status}) no cap "
                    f"{chapter_index}: {msg}"
                ) from exc

            parsed = getattr(resp, "parsed", None)
            if parsed is not None:
                break
            # Diagnostica por que veio None
            reasons = []
            for cand in (getattr(resp, "candidates", None) or []):
                fr = getattr(cand, "finish_reason", None)
                if fr is not None:
                    reasons.append(str(fr))
            pf = getattr(resp, "prompt_feedback", None)
            block_reason = getattr(pf, "block_reason", None) if pf else None
            last_err = (
                f"sem JSON parseado (finish_reason={reasons or '?'}, "
                f"block_reason={block_reason or 'none'})"
            )
            log.warning(
                "gemini_no_parsed",
                chapter=chapter_index,
                attempt=attempt,
                detail=last_err,
            )
            if attempt < 1:
                await asyncio.sleep(1.5)

        if parsed is None:
            raise GeminiTranslationError(
                f"Gemini falhou após 2 tentativas no capítulo {chapter_index}: {last_err}"
            )

        usage = getattr(resp, "usage_metadata", None) if resp else None
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0

        log.info(
            "gemini_translated",
            chapter=chapter_index,
            glossary_in=len(glossary),
            new_entries=len(parsed.new_glossary_entries),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return TranslationResult(
            translated_html=parsed.translated_html,
            translated_title=parsed.translated_title,
            new_entries=[
                GlossaryEntry(
                    term=d.term,
                    canonical_pt=d.canonical_pt,
                    kind=d.kind,
                    gender=d.gender,
                    notes=d.notes,
                    confidence=d.confidence,
                    first_seen_chapter=chapter_index,
                    source="llm",
                )
                for d in parsed.new_glossary_entries
            ],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
        )
