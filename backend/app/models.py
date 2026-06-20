"""Modelos de dominio que circulam entre as camadas (scraper -> cache -> epub).

Sao dataclasses puras, sem dependencia de SQLAlchemy. As tabelas ORM ficam
separadas em ``app/db/models.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Numero canonico do capitulo extraido do TITULO (ex: "Chapter 362 ..." -> 362).
# E a unica chave estavel ENTRE mirrors: a posicao/slug da URL diverge por
# off-by-N (um site insere/remove avisos), mas o numero no titulo bate. Usado
# pelo fallback de mirror pra casar "o cap 362 daqui" com "o cap 362 de la".
# Prioriza o numero APOS a palavra-chave (chapter/cap...) — assim "Volume 2
# Chapter 34" vira 34, nao 2. Sem palavra-chave, cai pro numero inicial.
_CH_KEYWORD_NUM = re.compile(
    r"\b(?:chapters?|chapt|chap|ch|cap[íi]tulos?|cap)\b\.?\s*[#:\-]?\s*(\d+)",
    re.IGNORECASE,
)
_LEADING_NUM = re.compile(r"^\s*[#:\-]?\s*(\d+)")


def parse_chapter_number(title: str | None) -> int | None:
    """Le o numero canonico do capitulo a partir do titulo. None se nao achar."""
    if not title:
        return None
    m = _CH_KEYWORD_NUM.search(title)
    if m:
        return int(m.group(1))
    m = _LEADING_NUM.match(title)
    if m:
        return int(m.group(1))
    return None


@dataclass(slots=True)
class ChapterRef:
    """Referencia a um capitulo, vinda da pagina indice (TOC) da novel."""

    index: int  # posicao 1-based dentro da novel
    title: str
    url: str
    # Volume ao qual esse cap pertence (ex: "Volume 3: Calamidade Vermelha").
    # Preenchido pelos adapters que organizam por volume (NovelMania). None se
    # adapter não detectar — UI cai pro modo manual de start/end.
    volume_label: str | None = None
    # Numero canonico lido do titulo (chave de casamento entre mirrors). Auto
    # computado de `title` no __post_init__ quando nao informado.
    number: int | None = None

    def __post_init__(self) -> None:
        if self.number is None:
            self.number = parse_chapter_number(self.title)


@dataclass(slots=True)
class ChapterContent:
    """Capitulo ja baixado e com o conteudo limpo."""

    index: int
    title: str  # titulo autoritativo (lido da propria pagina do capitulo)
    html: str  # corpo limpo: sequencia de <p>...</p>
    url: str


@dataclass(slots=True)
class NovelMeta:
    """Metadados da novel + lista ordenada de capitulos."""

    title: str
    source_url: str
    slug: str | None = None  # identidade estavel da novel no site (p/ o cache)
    author: str | None = None
    cover_url: str | None = None
    description: str | None = None
    chapters: list[ChapterRef] = field(default_factory=list)
