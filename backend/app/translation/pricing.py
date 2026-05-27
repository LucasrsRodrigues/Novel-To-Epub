"""Tabela de precos da Gemini API (USD).

Fonte: https://ai.google.dev/gemini-api/docs/pricing (mai 2026).
Valores em USD por 1M de tokens, exceto imagens que cobram por unidade.

Quando aparecer modelo novo nao mapeado, retorna 0 e loga warning (nao quebra
fluxo — so esmaece o numero do dashboard).
"""

from __future__ import annotations

from app.logging_conf import get_logger

log = get_logger("pricing")

# (input_usd_per_1m, output_usd_per_1m) — pra modelos por-token.
# Chaves aceitam tanto o modelo "puro" quanto com prefix "provider/modelo".
_TEXT_PRICES: dict[str, tuple[float, float]] = {
    # Gemini (Google)
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),  # ≤200k tokens; >200k usa 2.50/15.00
    # Groq (free tier disponível pra todos esses)
    "llama-3.3-70b-versatile": (0.0, 0.0),
    "llama-3.1-70b-versatile": (0.0, 0.0),
    "llama-3.1-8b-instant": (0.0, 0.0),
    # OpenRouter free models (sufixo :free)
    "qwen/qwen-2.5-72b-instruct:free": (0.0, 0.0),
    "meta-llama/llama-3.3-70b-instruct:free": (0.0, 0.0),
    "google/gemini-2.0-flash-exp:free": (0.0, 0.0),
    # Cerebras (free generoso)
    "llama-3.3-70b": (0.0, 0.0),
    "llama3.1-70b": (0.0, 0.0),
}

# Modelos cobrados por imagem gerada (token count e irrelevante)
_IMAGE_PRICES: dict[str, float] = {
    "gemini-2.5-flash-image": 0.039,  # $0.039/image (1024px)
}


def _normalize_model(model: str) -> str:
    """Tira prefix 'provider/' se presente, mas mantem sufixo ':free'."""
    return model.split("/", 1)[-1] if "/" in model else model


def calculate_cost(
    model: str, op: str, input_tokens: int, output_tokens: int,
) -> float:
    """Devolve custo em USD pra uma chamada. 0.0 se modelo desconhecido."""
    if op == "cover_image":
        price = _IMAGE_PRICES.get(model) or _IMAGE_PRICES.get(_normalize_model(model))
        if price is None:
            log.warning("pricing_unknown_image_model", model=model)
            return 0.0
        return price
    # Tenta exato (com prefix) primeiro, depois normalizado
    prices = _TEXT_PRICES.get(model) or _TEXT_PRICES.get(_normalize_model(model))
    if prices is None:
        log.warning("pricing_unknown_text_model", model=model)
        return 0.0
    in_usd = (input_tokens / 1_000_000) * prices[0]
    out_usd = (output_tokens / 1_000_000) * prices[1]
    return round(in_usd + out_usd, 6)
