"""CascadeTranslator: tenta lista de providers em ordem, com cooldown em rate-limit.

Fluxo:
  1. Se há pin de provider pro (novel, volume, lang) → tenta ele PRIMEIRO.
  2. Caso pin esteja em cooldown OU não exista, anda na lista ordenada.
  3. Para cada provider tentado:
     - Pula se em cooldown ativo (rate limit recente).
     - Tenta `translate_chapter`; se HTTP 429/5xx, marca cooldown e cai pro próximo.
     - Se sucesso, retorna e seta pin (se ainda sem).
  4. Se todos falharem → raise CascadeExhaustedError com último motivo.

Cooldown é in-memory (sumirá no restart do backend, ok — restart provavelmente
reseta o ratelimit lá tb por causa do tempo decorrido).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.logging_conf import get_logger
from app.translation.gemini_provider import GeminiTranslationError
from app.translation.glossary import GlossaryEntry
from app.translation.openai_compatible_provider import (
    OpenAICompatTranslationError,
)
from app.translation.pin_store import VolumePinStore
from app.translation.provider import TranslationProvider, TranslationResult

log = get_logger("cascade")


# Quanto tempo deixa provider em cooldown depois de bater rate-limit / erro.
# Free tier de TPM (tokens-per-minute) reseta em ~60s; 90s dá folga sem manter
# o provider preso por muito tempo. Se o response trouxer header Retry-After,
# ele tem precedência (provider sabe melhor que nós quando reset).
RATE_LIMIT_COOLDOWN = timedelta(seconds=90)
SERVER_ERROR_COOLDOWN = timedelta(seconds=30)


@dataclass
class _ProviderState:
    provider: TranslationProvider
    cooldown_until: datetime | None = None
    last_error: str | None = None

    def in_cooldown(self) -> bool:
        return (
            self.cooldown_until is not None
            and datetime.now(timezone.utc) < self.cooldown_until
        )


class CascadeExhaustedError(GeminiTranslationError):
    """Todos providers no cascade falharam — UI mostra como tradução perdida."""


class CascadeTranslator(TranslationProvider):
    """Wrap providers e implementa fallback automatico + pin."""

    name = "cascade"

    def __init__(
        self,
        providers: list[TranslationProvider],
        *,
        novel_id: int | None = None,
        volume_title: str | None = None,
    ) -> None:
        if not providers:
            raise ValueError("CascadeTranslator precisa de pelo menos 1 provider")
        # Mantem ORDEM como prioridade (mais barato/melhor primeiro)
        self._states: list[_ProviderState] = [_ProviderState(p) for p in providers]
        self._novel_id = novel_id
        self._volume_title = volume_title
        # model fica do primeiro (UI exibe — vai ser sobrescrito quando rodar)
        self.model = providers[0].model
        self._pin_store = VolumePinStore()

    def _ordered_for(
        self, language: str
    ) -> list[_ProviderState]:
        """Retorna providers na ordem efetiva pra esta tradução (pin → resto)."""
        order = list(self._states)
        if self._novel_id is None:
            return order
        pin = self._pin_store.get(self._novel_id, self._volume_title, language)
        if pin is None:
            return order
        pin_provider, pin_model = pin
        # Acha o state matchando provider+model e o move pra frente
        for i, st in enumerate(order):
            if st.provider.name == pin_provider and st.provider.model == pin_model:
                if i > 0:
                    order = [st] + order[:i] + order[i + 1 :]
                break
        else:
            # Pin aponta pra provider que não está mais configurado (usuário removeu).
            # Log mas segue normal.
            log.warning(
                "cascade_pin_provider_missing",
                novel_id=self._novel_id,
                volume_title=self._volume_title,
                pin_provider=pin_provider, pin_model=pin_model,
            )
        return order

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
        order = self._ordered_for(target_language)
        last_exc: Exception | None = None

        for state in order:
            if state.in_cooldown():
                log.debug(
                    "cascade_skip_cooldown",
                    provider=state.provider.name,
                    cooldown_until=state.cooldown_until.isoformat() if state.cooldown_until else None,
                )
                continue
            try:
                log.info(
                    "cascade_trying",
                    provider=state.provider.name, model=state.provider.model,
                    chapter=chapter_index,
                )
                result = await state.provider.translate_chapter(
                    text_html=text_html,
                    chapter_title=chapter_title,
                    target_language=target_language,
                    glossary=glossary,
                    novel_title=novel_title,
                    novel_slug=novel_slug,
                    chapter_index=chapter_index,
                    style_profile_block=style_profile_block,
                    style_anchor_block=style_anchor_block,
                )
                # Sucesso: pin (idempotente — preserva 1º) + limpa cooldown
                if self._novel_id is not None:
                    self._pin_store.set(
                        novel_id=self._novel_id,
                        volume_title=self._volume_title,
                        language=target_language,
                        provider=state.provider.name,
                        model=state.provider.model,
                    )
                state.cooldown_until = None
                state.last_error = None
                return result

            except OpenAICompatTranslationError as exc:
                last_exc = exc
                state.last_error = str(exc)[:200]
                self._record_failure(state, chapter_index, exc)
                code = exc.status_code
                # Retry-After do provider TEM PRIORIDADE sobre defaults nossos
                retry_after = getattr(exc, "retry_after_s", None)
                # 413 (request too large) do Groq = TPM-per-minute excedido,
                # mesma natureza de 429: reset em ~60s.
                if code in (429, 413):
                    duration = (
                        timedelta(seconds=retry_after) if retry_after
                        else RATE_LIMIT_COOLDOWN
                    )
                    state.cooldown_until = datetime.now(timezone.utc) + duration
                    log.warning(
                        "cascade_provider_ratelimited",
                        provider=state.provider.name, chapter=chapter_index,
                        code=code, cooldown_s=int(duration.total_seconds()),
                        from_header=retry_after is not None,
                    )
                elif code is not None and code >= 500:
                    duration = (
                        timedelta(seconds=retry_after) if retry_after
                        else SERVER_ERROR_COOLDOWN
                    )
                    state.cooldown_until = datetime.now(timezone.utc) + duration
                    log.warning(
                        "cascade_provider_server_error",
                        provider=state.provider.name, chapter=chapter_index,
                        code=code, cooldown_s=int(duration.total_seconds()),
                    )
                else:
                    # Erro do provider mas não dá pra recuperar com cooldown
                    # (parse fail, schema invalid, etc) — pula sem marcar tempo
                    log.warning(
                        "cascade_provider_other_error",
                        provider=state.provider.name, chapter=chapter_index,
                        error=state.last_error,
                    )
                continue

            except GeminiTranslationError as exc:
                # Erros do Gemini provider (que já vem com retry interno esgotado).
                # Trata como retryable temporário → cooldown curto.
                last_exc = exc
                state.last_error = str(exc)[:200]
                self._record_failure(state, chapter_index, exc)
                state.cooldown_until = datetime.now(timezone.utc) + SERVER_ERROR_COOLDOWN
                log.warning(
                    "cascade_provider_gemini_error",
                    provider=state.provider.name, chapter=chapter_index,
                    error=state.last_error,
                )
                continue

            except Exception as exc:
                # Imprevisto — não marca cooldown (pode ser bug nosso), só pula
                last_exc = exc
                state.last_error = str(exc)[:200]
                self._record_failure(state, chapter_index, exc)
                log.warning(
                    "cascade_provider_unexpected",
                    provider=state.provider.name, chapter=chapter_index,
                    error_type=type(exc).__name__, error=state.last_error,
                )
                continue

        # Esgotou — mensagem inclui ETA dos cooldowns pra UI saber quando "Continuar" funciona
        now = datetime.now(timezone.utc)
        cooldown_states = [s for s in order if s.in_cooldown()]
        soonest_s = None
        if cooldown_states:
            soonest_s = int(min(
                (s.cooldown_until - now).total_seconds() for s in cooldown_states
                if s.cooldown_until
            ))
        if last_exc is None:
            # Tudo em cooldown desde antes do loop começar — sem erro novo gerado
            msg = (
                f"todos os providers em cooldown no cap {chapter_index}. "
                f"aguarde ~{soonest_s}s e clique Continuar tradução."
            )
        else:
            cooldown_eta = (
                f" próximo provider disponível em ~{soonest_s}s." if soonest_s
                else ""
            )
            msg = (
                f"todos os providers falharam no cap {chapter_index}. "
                f"último erro: {last_exc}.{cooldown_eta}"
            )
        log.error(
            "cascade_exhausted",
            chapter=chapter_index, providers=len(order),
            cooldown_count=len(cooldown_states), soonest_s=soonest_s,
        )
        raise CascadeExhaustedError(msg) from last_exc

    def _record_failure(
        self, state: _ProviderState, chapter_index: int | None, exc: Exception
    ) -> None:
        """Grava tentativa-com-erro no UsageStore pra aparecer no Diagnóstico."""
        try:
            from app.db.usage_store import UsageStore
            UsageStore().record_failure(
                op="translate_chapter",
                model=state.provider.model,
                provider=state.provider.name,
                error_message=str(exc),
                novel_id=self._novel_id,
                chapter_index=chapter_index,
            )
        except Exception as record_exc:
            log.warning("cascade_record_failure_error", error=str(record_exc))

    def clear_cooldowns(self) -> int:
        """Reseta todos os cooldowns. Devolve quantos providers tinham cooldown ativo."""
        cleared = 0
        for st in self._states:
            if st.cooldown_until is not None:
                st.cooldown_until = None
                cleared += 1
        return cleared

    # Helper pra UI/debug
    def status(self) -> list[dict]:
        return [
            {
                "provider": st.provider.name,
                "model": st.provider.model,
                "in_cooldown": st.in_cooldown(),
                "cooldown_until": (
                    st.cooldown_until.isoformat() if st.cooldown_until else None
                ),
                "last_error": st.last_error,
            }
            for st in self._states
        ]
