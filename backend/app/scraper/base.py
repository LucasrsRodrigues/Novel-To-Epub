"""Interface base dos adapters de site (padrao Strategy)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional
from urllib.parse import urlparse

from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.cleaner import default_clean
from app.scraper.http import HttpClient
from app.scraper.registry import registry

# (done, total, label) — chamado pelo adapter durante fetch_novel quando a
# coleta de metadados eh demorada (paginacao da TOC, etc). Orchestrator
# repassa pro JobManager.on_progress -> UI ve "pagina 12/66" em vez de
# ficar olhando "0%" parado.
MetaProgressCb = Callable[[int, int, str], None]


class BaseAdapter(ABC):
    """Contrato que todo adapter de site precisa cumprir.

    Subclasses concretas se registram automaticamente no ``registry``.
    Apenas dois metodos sao obrigatorios; HTTP, rate-limit, cache e geracao
    de EPUB ficam fora do adapter.
    """

    #: nome curto/identificador (ex: "novelbin")
    name: str = ""
    #: dominios que este adapter atende (ex: ["novelbin.com"])
    domains: list[str] = []

    def __init__(self, client: HttpClient):
        self.client = client
        # Callback opcional pra reportar progresso durante fetch_novel.
        # Orchestrator seta apos o resolve. Adapter chama se setado.
        self.on_meta_progress: Optional[MetaProgressCb] = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # registra apenas classes concretas (sem metodos abstratos pendentes)
        if not getattr(cls, "__abstractmethods__", None):
            registry.register(cls)

    @classmethod
    def matches(cls, url: str) -> bool:
        """True se este adapter atende a URL (compara o host com ``domains``)."""
        host = (urlparse(url).netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return any(host == d or host.endswith("." + d) for d in cls.domains)

    @abstractmethod
    async def fetch_novel(self, url: str) -> NovelMeta:
        """Parseia a pagina da novel: metadados + lista ordenada de capitulos.

        Deve lidar internamente com paginacao da TOC, se houver.
        """

    @abstractmethod
    async def fetch_chapter(self, ref: ChapterRef) -> ChapterContent:
        """Baixa e parseia um capitulo, devolvendo HTML ja limpo."""

    # Hook opcional: limpeza padrao compartilhada; override por site se preciso.
    def clean(self, raw_html: str) -> str:
        return default_clean(raw_html)
