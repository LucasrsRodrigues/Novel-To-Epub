"""Registry de adapters + auto-discovery.

Cada subclasse concreta de ``BaseAdapter`` se registra sozinha (via
``__init_subclass__``). O ``discover()`` importa todos os modulos da pasta
``adapters/``, entao **adicionar um site = criar um arquivo la**, sem editar
nada aqui.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

from app.scraper.errors import UnsupportedSiteError

if TYPE_CHECKING:
    from app.scraper.base import BaseAdapter
    from app.scraper.http import HttpClient


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: list[type[BaseAdapter]] = []
        self._discovered = False

    def register(self, adapter_cls: type[BaseAdapter]) -> None:
        if adapter_cls not in self._adapters:
            self._adapters.append(adapter_cls)

    @property
    def adapters(self) -> list[type[BaseAdapter]]:
        self.discover()
        return list(self._adapters)

    def discover(self) -> None:
        """Importa todos os modulos de ``app.scraper.adapters`` (idempotente)."""
        if self._discovered:
            return
        from app.scraper import adapters as pkg

        for _, modname, _ in pkgutil.iter_modules(pkg.__path__):
            importlib.import_module(f"{pkg.__name__}.{modname}")
        self._discovered = True

    def resolve(self, url: str, client: HttpClient) -> BaseAdapter:
        """Retorna uma instancia do adapter que reconhece ``url``."""
        self.discover()
        for adapter_cls in self._adapters:
            if adapter_cls.matches(url):
                return adapter_cls(client)
        raise UnsupportedSiteError(url)

    def supports(self, url: str) -> bool:
        """True se algum adapter registrado reconhece a URL (sem instanciar)."""
        self.discover()
        return any(adapter_cls.matches(url) for adapter_cls in self._adapters)


# Singleton usado pelo __init_subclass__ dos adapters.
registry = AdapterRegistry()
