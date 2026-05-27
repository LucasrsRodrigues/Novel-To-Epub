"""Modelos de dominio que circulam entre as camadas (scraper -> cache -> epub).

Sao dataclasses puras, sem dependencia de SQLAlchemy. As tabelas ORM ficam
separadas em ``app/db/models.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
