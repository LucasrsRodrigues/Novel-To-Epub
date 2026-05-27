"""Limpeza generica de conteudo de capitulo.

Recebe o HTML do container de conteudo (extraido pelo adapter) e devolve uma
sequencia de ``<p>`` limpos: sem scripts/ads e sem frases de spam tipo
"read the latest chapter at site.com".

A limpeza e generica de proposito; cada adapter pode sobrescrever ``clean``
para regras especificas do site.
"""

from __future__ import annotations

import re
from html import escape

from bs4 import BeautifulSoup

# Tags inteiras que nunca sao conteudo.
REMOVE_TAGS = ["script", "style", "ins", "iframe", "noscript", "button", "svg", "form"]

# Palavras-chave em class/id que indicam ads/widgets (token-based, conservador).
AD_KEYWORDS = (
    "advert",
    "banner",
    "promo",
    "sharethis",
    "social-share",
    "newsletter",
    "subscribe",
    "adsbygoogle",
)

# Frases de spam comuns em paragrafos de novels piratas.
SPAM_PATTERNS = [
    re.compile(r"read\s+.{0,40}\b(at|on)\b\s+\S+\.(com|net|org|io)", re.I),
    re.compile(r"visit\s+\S+\.(com|net|org|io)", re.I),
    re.compile(r"please\s+(support|read|visit|bookmark)", re.I),
    re.compile(r"latest\s+chapters?\s+(at|on)\b", re.I),
    re.compile(r"find\s+(the\s+)?(latest|updated)\s+.{0,30}(at|on)\b", re.I),
]


def _is_ad(el) -> bool:
    classes = " ".join(el.get("class", [])) if el.has_attr("class") else ""
    el_id = el.get("id", "") or ""
    attrs = f"{classes} {el_id}".lower()
    return any(kw in attrs for kw in AD_KEYWORDS)


def _is_spam(text: str) -> bool:
    return any(pat.search(text) for pat in SPAM_PATTERNS)


def default_clean(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "lxml")

    for tag in soup.find_all(REMOVE_TAGS):
        tag.decompose()

    for el in soup.find_all(True):
        if _is_ad(el):
            el.decompose()

    paragraphs: list[str] = []
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if text and not _is_spam(text):
            paragraphs.append(text)

    # Fallback: alguns sites nao usam <p>, soltam texto direto no container.
    if not paragraphs:
        raw_text = soup.get_text("\n", strip=True)
        paragraphs = [
            line
            for line in (ln.strip() for ln in raw_text.split("\n"))
            if line and not _is_spam(line)
        ]

    return "\n".join(f"<p>{escape(t)}</p>" for t in paragraphs)
