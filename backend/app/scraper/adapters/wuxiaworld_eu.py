"""Adapter para WuxiaWorldEU (wuxiaworld.eu) — nao confundir com wuxiaworld.com.

O site e Next.js e cada pagina traz os dados ja prontos no JSON do
``<script id="__NEXT_DATA__">`` — o adapter le esse JSON em vez de raspar o
HTML renderizado (bem mais estavel que seletor CSS). Mapeado em 2026-10-11:

  - Novel: ``/novel-detail/<slug>`` (ou ``/novel/<slug>``)
      props.pageProps.novel → title, description, status, author.name,
        coverOriginal (caminho no CDN), firstChapterNumber, chapterCount
      props.pageProps.toc   → items [{number, title}] de 100 em 100,
        ranges [{page, from, to}] com todas as paginas
  - Paginas da TOC: ``/novel/<slug>?page=N``
  - Capitulo: ``/chapter/<slug>-<numero>``
      props.pageProps.data.chapter → {number, title, paragraphs: [str, ...]}
      ``paragraphs`` vem em TEXTO PURO (sem tags), um item por paragrafo.
  - Capa original (JPEG): ``https://cdn.wuxiaworld.eu/<coverOriginal>`` (o campo
    ja vem com o prefixo ``original/``)

Detalhes:
- ``index`` = numero do capitulo no site (relativo ao primeiro), nao a posicao
  na lista — o cache de capitulos/traducao e chaveado por index, e um indice
  posicional desalinharia se o site inserisse/removesse capitulos.
- Titulos trazem o volume ("Volume 3 Chapter 169 - ...") → ``volume_label``,
  que a UI usa pra oferecer captura por volume — e o prefixo sai do titulo
  ("Chapter 169 - ..."): o volume ja e o proprio EPUB, e o builder so tira o
  "Chapter N" quando ele vem no comeco.
- Alguns capitulos repetem o titulo como 1o paragrafo; esse paragrafo sai
  (senao aparece duplicado embaixo do cabecalho do capitulo).
"""

from __future__ import annotations

import asyncio
import json
import re
from html import escape
from urllib.parse import urlparse

from app.logging_conf import get_logger
from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.base import BaseAdapter
from app.scraper.cleaner import is_spam
from app.scraper.errors import ParseError

log = get_logger("wuxiaworld_eu")

_BASE = "https://wuxiaworld.eu"
_CDN = "https://cdn.wuxiaworld.eu"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_NOVEL_PATH = re.compile(r"^/(?:novel-detail|novel)/(?P<slug>[^/?#]+)")
_CHAPTER_PATH = re.compile(r"^/chapter/(?P<slug>.+)-(?P<num>\d+)/?$")
_VOLUME = re.compile(r"^\s*(Volume\s+\d+)\b\s*[-–:.]?\s*", re.I)
# Paginas da TOC buscadas em paralelo (leves, mesmo backend) — sem exagero.
_TOC_CONCURRENCY = 4


class WuxiaWorldEUAdapter(BaseAdapter):
    name = "wuxiaworld_eu"
    domains = ["wuxiaworld.eu"]

    async def fetch_novel(self, url: str) -> NovelMeta:
        slug = _novel_slug(url)
        if not slug:
            raise ParseError(f"nao consegui extrair o slug da URL: {url}")
        props = await self._page_props(f"{_BASE}/novel-detail/{slug}")
        novel = props.get("novel")
        toc = props.get("toc")
        if not isinstance(novel, dict) or not isinstance(toc, dict):
            raise ParseError(f"pagina da novel sem 'novel'/'toc' no __NEXT_DATA__: {slug}")

        first = _as_int(novel.get("firstChapterNumber"))
        if first is None:
            first = 1
        items: dict[int, dict] = {}
        _collect(items, toc.get("items"))

        # Demais paginas da TOC (a 1a ja veio junto com a novel).
        pages = sorted(
            {p for p in (_as_int(r.get("page")) for r in toc.get("ranges") or []) if p and p > 1}
        )
        total_pages = len(pages) + 1
        done = 1
        self._report(done, total_pages)
        sem = asyncio.Semaphore(_TOC_CONCURRENCY)

        async def fetch_page(page: int) -> None:
            nonlocal done
            async with sem:
                p = await self._page_props(
                    f"{_BASE}/novel/{slug}?page={page}", throttle=False
                )
            _collect(items, (p.get("toc") or {}).get("items"))
            done += 1
            self._report(done, total_pages)

        await asyncio.gather(*[fetch_page(p) for p in pages])

        chapters = [
            ChapterRef(
                index=num - first + 1,
                title=_strip_volume(it.get("title")) or f"Chapter {num}",
                url=f"{_BASE}/chapter/{slug}-{num}",
                volume_label=_volume_of(it.get("title")),
            )
            for num, it in sorted(items.items())
            if num >= first
        ]
        if not chapters:
            raise ParseError(f"nenhum capitulo listado para {slug}")

        cover = novel.get("coverOriginal")
        author = novel.get("author") if isinstance(novel.get("author"), dict) else {}
        meta = NovelMeta(
            title=(novel.get("title") or slug).strip(),
            source_url=f"{_BASE}/novel-detail/{slug}",
            slug=slug,
            author=(author.get("name") or "").strip() or None,
            cover_url=f"{_CDN}/{cover.lstrip('/')}" if cover else None,
            description=(novel.get("description") or "").strip() or None,
            chapters=chapters,
        )
        expected = _as_int(novel.get("chapterCount"))
        log.info(
            "novel_parsed", title=meta.title, chapters=len(chapters),
            expected=expected, toc_pages=total_pages, status=novel.get("status"),
        )
        return meta

    async def fetch_chapter(self, ref: ChapterRef) -> ChapterContent:
        if not _CHAPTER_PATH.match(urlparse(ref.url).path):
            raise ParseError(f"URL de capitulo fora do padrao esperado: {ref.url}")
        props = await self._page_props(ref.url)
        data = props.get("data") if isinstance(props.get("data"), dict) else {}
        chapter = data.get("chapter")
        if not isinstance(chapter, dict):
            raise ParseError(f"capitulo sem 'data.chapter' no __NEXT_DATA__: {ref.url}")
        paragraphs = chapter.get("paragraphs")
        if not isinstance(paragraphs, list) or not paragraphs:
            raise ParseError(f"capitulo veio sem paragrafos: {ref.url}")
        raw_title = (chapter.get("title") or "").strip()
        if paragraphs and _repeats_title(str(paragraphs[0]), raw_title):
            paragraphs = paragraphs[1:]
        html = self.clean(paragraphs)
        if not html:
            raise ParseError(f"capitulo vazio depois da limpeza: {ref.url}")
        return ChapterContent(
            index=ref.index,
            title=_strip_volume(raw_title) or ref.title,
            html=html,
            url=ref.url,
        )

    def clean(self, paragraphs: list) -> str:  # type: ignore[override]
        """Lista de paragrafos em texto puro → ``<p>`` escapados.

        Nao passa pelo ``default_clean`` (que espera HTML): um ``<`` legitimo
        da prosa ("<You have learned Fireball>", mensagem de sistema) viraria
        tag e sumiria. Reusa so o filtro de spam.
        """
        out = []
        for p in paragraphs:
            text = str(p).strip()
            if text and not is_spam(text):
                out.append(f"<p>{escape(text)}</p>")
        return "\n".join(out)

    # ------------------------------------------------------------------ helpers
    async def _page_props(self, url: str, *, throttle: bool = True) -> dict:
        html = await self.client.get_text(url, throttle=throttle)
        m = _NEXT_DATA.search(html)
        if not m:
            raise ParseError(f"pagina sem __NEXT_DATA__ (o site mudou?): {url}")
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            raise ParseError(f"__NEXT_DATA__ invalido em {url}: {exc}") from exc
        props = (data.get("props") or {}).get("pageProps")
        if not isinstance(props, dict):
            raise ParseError(f"__NEXT_DATA__ sem pageProps: {url}")
        return props

    def _report(self, done: int, total: int) -> None:
        if self.on_meta_progress is not None and total > 1:
            self.on_meta_progress(done, total, f"Buscando lista de capítulos · página {done}/{total}")


def _collect(into: dict[int, dict], items) -> None:
    for it in items or []:
        num = _as_int(it.get("number")) if isinstance(it, dict) else None
        if num is not None:
            into[num] = it


def _volume_of(title: str | None) -> str | None:
    m = _VOLUME.match(title or "")
    return m.group(1).title() if m else None


def _strip_volume(title: str | None) -> str:
    """"Volume 1 Chapter 102 - X" → "Chapter 102 - X" (sem mexer no resto)."""
    t = (title or "").strip()
    stripped = _VOLUME.sub("", t, count=1).strip()
    return stripped or t


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", " ", s).strip().lower()


def _repeats_title(first_paragraph: str, title: str) -> bool:
    """1o paragrafo curto que e (ou comeca com) o proprio titulo do capitulo."""
    p = first_paragraph.strip()
    if not title or len(p) > 200:
        return False
    np, nt = _norm(p), _norm(title)
    return bool(nt) and (np == nt or np.startswith(nt))


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _novel_slug(url: str) -> str | None:
    """Aceita /novel-detail/<slug>, /novel/<slug> e /chapter/<slug>-<n>."""
    path = urlparse(url).path
    m = _NOVEL_PATH.match(path)
    if m:
        return m.group("slug")
    m = _CHAPTER_PATH.match(path)
    return m.group("slug") if m else None
