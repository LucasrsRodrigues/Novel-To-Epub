"""Adapter para Royal Road (royalroad.com).

Estrutura do site (mapeada em 2026-05):
  - Pagina da ficcao: ``/fiction/<id>/<slug>``
      titulo  -> ``.fic-title h1`` (fallback ``h1``)
      autor   -> ``h4 a[href^="/profile/"]``
      capa    -> ``meta[property="og:image"]`` (CDN absoluta)
      desc    -> ``.description``
      caps    -> JSON embutido ``window.chapters = [...]`` (lista COMPLETA, sem
                 paginacao — cada item tem title/url/order/visible). Fallback:
                 tabela ``table#chapters tbody tr a``.
  - Pagina do capitulo: ``/fiction/<id>/<slug>/chapter/<cid>/<cslug>``
      titulo  -> ``h1``
      corpo   -> ``.chapter-inner.chapter-content`` (default_clean basta)

Royal Road e em ingles → tradutor entra normal (nao e PT-nativo).

NOTA: o site as vezes injeta paragrafos anti-pirataria escondidos via CSS da
propria pagina. O default_clean nao os remove (ficam como <p> normais no HTML).
Se aparecer texto-lixo no meio dos capitulos, tratar aqui no clean().
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.logging_conf import get_logger
from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.base import BaseAdapter
from app.scraper.errors import ParseError

log = get_logger("royalroad")

# Captura o array JSON de ``window.chapters = [ ... ];`` (uma linha logica).
_CHAPTERS_JS_RE = re.compile(r"window\.chapters\s*=\s*(\[.*?\])\s*;", re.S)
# Id numerico estavel da ficcao em ``/fiction/<id>/...``
_FICTION_ID_RE = re.compile(r"/fiction/(\d+)")

# --- Anti-pirataria do Royal Road ---
# O RR injeta um <span> (dentro de um <p> legitimo) com um aviso tipo "if you
# discover this on Amazon, report it". Ele e ESCONDIDO via CSS: uma classe
# ALEATORIA por request recebe ``display:none`` num <style> da pagina. Como o
# default_clean achata o HTML, o texto do span vazaria pro paragrafo e poluiria
# a traducao. Solucao: ler as classes que o <style> esconde e remover esses
# elementos do conteudo ANTES de limpar — pega o lixo independente do nome
# aleatorio, da tag ou do texto do aviso.
_CSS_RULE_RE = re.compile(r"\.([\w-]+)\s*\{([^}]*)\}")
_HIDDEN_DECL_RE = re.compile(
    r"(display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0|"
    r"font-size\s*:\s*0|height\s*:\s*0|speak\s*:\s*never)",
    re.I,
)


def _hidden_class_names(soup: BeautifulSoup) -> set[str]:
    """Classes que algum <style> da pagina esconde (display:none, etc.)."""
    names: set[str] = set()
    for st in soup.find_all("style"):
        css = st.string or st.get_text()
        if not css:
            continue
        for m in _CSS_RULE_RE.finditer(css):
            if _HIDDEN_DECL_RE.search(m.group(2)):
                names.add(m.group(1))
    return names


def _strip_hidden_nodes(content, hidden: set[str]) -> int:
    """Remove do conteudo os elementos cuja classe esta escondida via CSS.

    Retorna quantos removeu. ``find_all`` devolve um snapshot, entao decompor
    durante a iteracao e seguro.
    """
    if not hidden:
        return 0
    removed = 0
    for el in content.find_all(class_=True):
        if hidden.intersection(el.get("class") or []):
            el.decompose()
            removed += 1
    return removed


class RoyalRoadAdapter(BaseAdapter):
    name = "royalroad"
    domains = ["royalroad.com"]

    async def fetch_novel(self, url: str) -> NovelMeta:
        soup = BeautifulSoup(await self.client.get_text(url), "lxml")

        title_el = soup.select_one(".fic-title h1") or soup.select_one("h1")
        if title_el is None:
            raise ParseError(f"titulo da novel nao encontrado em {url}")
        title = title_el.get_text(" ", strip=True)

        chapters = _extract_chapters(soup, url)
        if not chapters:
            raise ParseError(f"lista de capitulos vazia: {url}")

        meta = NovelMeta(
            title=title,
            source_url=url,
            slug=_slug_from_url(url),
            author=_extract_author(soup),
            cover_url=_extract_cover(soup, url),
            description=_extract_description(soup),
            chapters=chapters,
        )
        log.info(
            "novel_parsed",
            title=meta.title, author=meta.author,
            chapters=len(meta.chapters), slug=meta.slug,
        )
        return meta

    async def fetch_chapter(self, ref: ChapterRef) -> ChapterContent:
        soup = BeautifulSoup(await self.client.get_text(ref.url), "lxml")

        title_el = soup.select_one("h1")
        title = title_el.get_text(" ", strip=True) if title_el else ref.title

        content_el = soup.select_one(".chapter-inner.chapter-content") or soup.select_one(
            ".chapter-content"
        )
        if content_el is None:
            raise ParseError(f"conteudo do capitulo nao encontrado em {ref.url}")

        # Remove o aviso anti-pirataria que o RR injeta escondido via CSS antes
        # de achatar o HTML (senao o texto vaza pro paragrafo e vai pra traducao).
        removed = _strip_hidden_nodes(content_el, _hidden_class_names(soup))
        if removed:
            log.debug("royalroad_stripped_hidden", count=removed, url=ref.url)

        return ChapterContent(
            index=ref.index,
            title=title,
            html=self.clean(str(content_el)),
            url=ref.url,
        )


# --------------------------- helpers de parse ------------------------------


def _slug_from_url(url: str) -> str:
    """Id numerico da ficcao (``/fiction/<id>/...``) como identidade estavel."""
    m = _FICTION_ID_RE.search(urlparse(url).path)
    return m.group(1) if m else "royalroad"


def _extract_author(soup: BeautifulSoup) -> str | None:
    el = soup.select_one('h4 a[href^="/profile/"]') or soup.select_one(
        'a[href^="/profile/"]'
    )
    return el.get_text(" ", strip=True) or None if el else None


def _extract_cover(soup: BeautifulSoup, base_url: str) -> str | None:
    meta = soup.select_one('meta[property="og:image"]')
    if meta and meta.get("content"):
        return urljoin(base_url, meta["content"])
    img = soup.select_one(".cover-art-container img[src], img.thumbnail[src]")
    if img and img.get("src"):
        return urljoin(base_url, img["src"])
    return None


def _extract_description(soup: BeautifulSoup) -> str | None:
    el = soup.select_one(".description")
    return el.get_text("\n", strip=True) or None if el else None


def _extract_chapters(soup: BeautifulSoup, base_url: str) -> list[ChapterRef]:
    """Lista de capitulos. Primario: JSON ``window.chapters``; fallback: tabela."""
    refs = _chapters_from_json(soup, base_url)
    if not refs:
        refs = _chapters_from_table(soup, base_url)
    # Renumera 1..N na ordem coletada (ja vem cronologica).
    for i, ref in enumerate(refs, start=1):
        ref.index = i
    return refs


def _chapters_from_json(soup: BeautifulSoup, base_url: str) -> list[ChapterRef]:
    """Le o array ``window.chapters`` embutido num <script>."""
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if not text or "window.chapters" not in text:
            continue
        m = _CHAPTERS_JS_RE.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            log.warning("chapters_json_decode_failed", error=str(exc))
            return []
        # Ordena por `order`; mantem apenas visiveis; precisa de url + title.
        items = sorted(
            (c for c in data if c.get("visible", 1) and c.get("url")),
            key=lambda c: c.get("order", 0),
        )
        return [
            ChapterRef(
                index=0,
                title=(c.get("title") or "").strip() or f"Chapter {i + 1}",
                url=urljoin(base_url, c["url"]),
            )
            for i, c in enumerate(items)
        ]
    return []


def _chapters_from_table(soup: BeautifulSoup, base_url: str) -> list[ChapterRef]:
    """Fallback: linhas da tabela ``table#chapters``."""
    refs: list[ChapterRef] = []
    for a in soup.select("table#chapters tbody tr td a[href*='/chapter/']"):
        href = a.get("href")
        title = a.get_text(" ", strip=True)
        if href and title:
            refs.append(ChapterRef(index=0, title=title, url=urljoin(base_url, href)))
    return refs
