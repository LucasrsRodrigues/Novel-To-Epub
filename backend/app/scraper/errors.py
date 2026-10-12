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
    """Falha ao baixar uma pagina (rede/HTTP).

    ``status`` traz o codigo HTTP quando a falha veio de uma resposta (None em
    erro de transporte/DNS). Adapters que falam com API JSON usam isso pra
    distinguir 401/403/404 sem ter que ler a mensagem.
    """

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class ParseError(ScraperError):
    """Falha ao extrair dados do HTML (estrutura mudou?)."""


class BlockedError(FetchError):
    """O site respondeu com um desafio anti-bot (ex.: Cloudflare 'Just a moment')."""
