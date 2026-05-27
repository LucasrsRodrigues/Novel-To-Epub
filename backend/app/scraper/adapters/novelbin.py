"""Adapter para NovelBin (novelbin.com / .me / .net / mirrors).

Estrutura do site (mapeada em 2026-05):
  - Pagina da novel: ``/novel-book/<slug>``
      titulo  -> ``h3.title``
      slug    -> ``#rating[data-novel-id]`` (e o slug, nao um id numerico)
      autor   -> ``ul.info li`` com label "Author"
      capa    -> ``meta[itemprop=image]`` / ``meta[property=og:image]``
      desc    -> ``div.desc-text``
  - Lista COMPLETA de capitulos vem via AJAX (a pagina so traz ~30):
      ``/ajax/chapter-archive?novelId=<slug>``  ->  <a title=.. href=..>
  - Pagina do capitulo: ``/novel-book/<slug>/<chap-slug>``
      titulo  -> ``a.chr-title``
      corpo   -> ``#chr-content`` (== ``.chr-c``)

Quirk: textos de "sistema" guardam < e > como ``\\u003c`` / ``\\u003e``
literais. Decodificamos isso apos a limpeza (ver ``clean``).
"""

from __future__ import annotations

import re
from html import escape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.logging_conf import get_logger
from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.base import BaseAdapter
from app.scraper.errors import ParseError

log = get_logger("novelbin")

# sequencias \uXXXX (escape estilo JS) deixadas literais no texto
_UNICODE_ESC = re.compile(r"\\u([0-9a-fA-F]{4})")


class NovelBinAdapter(BaseAdapter):
    name = "novelbin"
    domains = ["novelbin.com", "novelbin.me", "novelbin.net", "novelbin.org", "novelbin.io"]

    async def fetch_novel(self, url: str) -> NovelMeta:
        soup = BeautifulSoup(await self.client.get_text(url), "lxml")

        title_el = soup.select_one("h3.title")
        if title_el is None:
            raise ParseError(f"titulo da novel nao encontrado em {url}")
        title = title_el.get_text(strip=True)

        slug_el = soup.select_one("#rating[data-novel-id]")
        slug = slug_el["data-novel-id"] if slug_el else _slug_from_url(url)

        meta = NovelMeta(
            title=title,
            source_url=url,
            slug=slug,
            author=self._extract_info(soup, "author"),
            cover_url=self._extract_cover(soup, url),
            description=self._extract_description(soup),
            chapters=await self._fetch_chapter_list(url, slug),
        )
        log.info(
            "novel_parsed",
            title=meta.title,
            author=meta.author,
            chapters=len(meta.chapters),
        )
        return meta

    async def fetch_chapter(self, ref: ChapterRef) -> ChapterContent:
        soup = BeautifulSoup(await self.client.get_text(ref.url), "lxml")

        title_el = soup.select_one("a.chr-title, .chr-title")
        title = title_el.get_text(" ", strip=True) if title_el else ref.title

        content_el = soup.select_one("#chr-content, .chr-c")
        if content_el is None:
            raise ParseError(f"conteudo do capitulo nao encontrado em {ref.url}")

        return ChapterContent(
            index=ref.index,
            title=title,
            html=self.clean(str(content_el)),
            url=ref.url,
        )

    def clean(self, raw_html: str) -> str:
        # Limpeza padrao (extrai <p>, remove ads/spam, escapa) e DEPOIS converte
        # os \uXXXX literais para a entidade HTML correspondente. Fazer por ultimo
        # evita que um < vire "<" antes do parse e seja lido como tag.
        cleaned = super().clean(raw_html)
        return _UNICODE_ESC.sub(lambda m: escape(chr(int(m.group(1), 16))), cleaned)

    # ------------------------------------------------------------------ helpers
    async def _fetch_chapter_list(self, url: str, slug: str) -> list[ChapterRef]:
        base = _base(url)
        ajax = f"{base}/ajax/chapter-archive?novelId={slug}"
        soup = BeautifulSoup(await self.client.get_text(ajax), "lxml")

        refs: list[ChapterRef] = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            ctitle = (a.get("title") or a.get_text(" ", strip=True)).strip()
            if href:
                refs.append(
                    ChapterRef(index=len(refs) + 1, title=ctitle, url=urljoin(base, href))
                )
        if not refs:
            raise ParseError(f"lista de capitulos vazia: {ajax}")
        return refs

    def _extract_info(self, soup: BeautifulSoup, label: str) -> str | None:
        info = soup.select_one("ul.info, ul.info-meta, .info-meta")
        if info is None:
            return None
        for li in info.find_all("li"):
            head = li.find("h3")
            if head and label.lower() in head.get_text(strip=True).lower():
                value = li.find("a")
                if value:
                    return value.get_text(strip=True) or None
                return li.get_text(" ", strip=True).split(":", 1)[-1].strip() or None
        return None

    def _extract_cover(self, soup: BeautifulSoup, url: str) -> str | None:
        for sel in ('meta[itemprop="image"]', 'meta[property="og:image"]'):
            el = soup.select_one(sel)
            if el and el.get("content"):
                return urljoin(url, el["content"])
        img = soup.select_one(".book img, .books img")
        if img and img.get("src"):
            return urljoin(url, img["src"])
        return None

    def _extract_description(self, soup: BeautifulSoup) -> str | None:
        el = soup.select_one("div.desc-text, .desc-text")
        return el.get_text("\n", strip=True) if el else None


def _base(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _slug_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
