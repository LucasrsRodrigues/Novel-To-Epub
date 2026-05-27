"""Excecoes da camada de scraping (modulo separado p/ evitar import circular)."""

from __future__ import annotations


class ScraperError(Exception):
    """Erro generico de scraping."""


class UnsupportedSiteError(ScraperError):
    """Nenhum adapter registrado reconhece a URL."""

    def __init__(self, url: str):
        super().__init__(f"Nenhum adapter encontrado para a URL: {url}")
        self.url = url


class FetchError(ScraperError):
    """Falha ao baixar uma pagina (rede/HTTP)."""


class ParseError(ScraperError):
    """Falha ao extrair dados do HTML (estrutura mudou?)."""
