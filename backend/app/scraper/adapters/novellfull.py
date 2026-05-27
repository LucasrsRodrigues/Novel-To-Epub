"""Adapter para NovelFull (novelfull.net).

Estrutura do site (mapeada em 2026-05):
  - Pagina da novel: ``/<slug>.html``
      titulo  -> ``h3.title``
      autor   -> ``.info`` (label "Author:" seguido de <a>)
      capa    -> ``.book img`` (path relativo, precisa urljoin)
      desc    -> ``.desc-text``
      caps    -> ``ul.list-chapter li a`` (50 por pagina)
      pag     -> ``.pagination`` com ``Last »`` apontando ``?page=N``
  - Pagina do capitulo: ``/<slug>/<chap-slug>.html``
      titulo  -> ``.chapter-title`` (h2)
      corpo   -> ``#chapter-content`` (default_clean basta — limpa ads/scripts)

A TOC e paginada: novel media tem ~60 paginas. Buscamos a pagina 1, descobrimos
o total via ``Last »`` e baixamos as restantes em sequencia (o HttpClient ja
serializa via lock + rate-limit).
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.logging_conf import get_logger
from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.base import BaseAdapter
from app.scraper.errors import ParseError

log = get_logger("novelfull")

# Extrai o numero N de ``?page=N`` (qualquer posicao na querystring).
_PAGE_QS_RE = re.compile(r"[?&]page=(\d+)")

# Paralelismo da paginacao da TOC. Cada request eh um SSR barato e o site
# aguenta — testes mostram que 8 em paralelo nao causa rate-limit nem 503.
# Acima disso comeca a ter risco e ganho marginal cai.
_TOC_CONCURRENCY = 8


class NovelFullAdapter(BaseAdapter):
    name = "novelfull"
    domains = ["novelfull.net"]

    async def fetch_novel(self, url: str) -> NovelMeta:
        soup = BeautifulSoup(await self.client.get_text(url), "lxml")

        title_el = soup.select_one("h3.title")
        if title_el is None:
            raise ParseError(f"titulo da novel nao encontrado em {url}")
        title = title_el.get_text(" ", strip=True)

        chapters = await self._fetch_all_chapter_refs(soup, url)

        meta = NovelMeta(
            title=title,
            source_url=url,
            slug=_slug_from_url(url),
            author=_extract_info(soup, "author"),
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

        title_el = soup.select_one(".chapter-title")
        title = title_el.get_text(" ", strip=True) if title_el else ref.title

        content_el = soup.select_one("#chapter-content")
        if content_el is None:
            raise ParseError(f"conteudo do capitulo nao encontrado em {ref.url}")

        return ChapterContent(
            index=ref.index,
            title=title,
            html=self.clean(str(content_el)),
            url=ref.url,
        )

    # ------------------------------------------------------------------ helpers

    async def _fetch_all_chapter_refs(
        self, first_soup: BeautifulSoup, url: str
    ) -> list[ChapterRef]:
        """Coleta capitulos de todas as paginas da TOC, em ordem.

        Recebe a soup da pagina 1 (ja baixada por ``fetch_novel``) pra
        evitar um request duplicado. Paginas 2..N saem em paralelo (semaforo
        de ``_TOC_CONCURRENCY``) com ``throttle=False`` — a TOC eh leve e
        serializar com delay 1-3s/pagina torna novel de 60 paginas inviavel
        (~130s). Em paralelo cai pra ~10-15s.
        """
        refs_by_page: dict[int, list[ChapterRef]] = {
            1: _extract_chapters_from_page(first_soup, url)
        }
        last_page = _detect_last_page(first_soup)
        total_pages = last_page

        # Reporta progresso da pg1 ja coletada.
        self._report_meta(1, total_pages)

        if last_page > 1:
            base = url.split("?", 1)[0]
            sem = asyncio.Semaphore(_TOC_CONCURRENCY)
            done_pages = 1  # pg1 ja contabilizada
            lock = asyncio.Lock()

            async def fetch_page(page: int) -> None:
                nonlocal done_pages
                async with sem:
                    page_url = f"{base}?page={page}"
                    html = await self.client.get_text(page_url, throttle=False)
                    page_soup = BeautifulSoup(html, "lxml")
                    chapters = _extract_chapters_from_page(page_soup, page_url)
                async with lock:
                    refs_by_page[page] = chapters
                    done_pages += 1
                    self._report_meta(done_pages, total_pages)

            await asyncio.gather(*[fetch_page(p) for p in range(2, last_page + 1)])

        # Concatena na ordem das paginas (dict ordenado nao garante; ordeno).
        refs: list[ChapterRef] = []
        for page in sorted(refs_by_page.keys()):
            refs.extend(refs_by_page[page])

        if not refs:
            raise ParseError(f"lista de capitulos vazia: {url}")

        # Renumera 1..N (anchors ja vem em ordem cronologica em cada pagina).
        for i, ref in enumerate(refs, start=1):
            ref.index = i
        return refs

    def _report_meta(self, done: int, total: int) -> None:
        if self.on_meta_progress is not None:
            label = f"Buscando lista de capítulos · página {done}/{total}"
            self.on_meta_progress(done, total, label)


# --------------------------- helpers de parse ------------------------------


def _slug_from_url(url: str) -> str:
    """Extrai o slug da novel a partir da URL.

    Funciona tanto para URL da novel (``/<slug>.html``) quanto de capitulo
    (``/<slug>/<chap-slug>.html``).
    """
    path = urlparse(url).path.strip("/")
    if path.endswith(".html"):
        path = path[:-5]
    return path.split("/", 1)[0] or "novel"


def _extract_info(soup: BeautifulSoup, label: str) -> str | None:
    """Le o ``<div class="info">`` que vem como pares header + valor:

    .. code-block:: html

       <div class="info">
         <div><h3>Author:</h3> <a>Awespec</a></div>
         <div><h3>Genres:</h3> <a>Fantasy</a>, <a>Adventure</a></div>
         <div><h3>Status:</h3> Ongoing</div>
       </div>

    Procura o ``<h3>`` cujo texto contem ``label`` e junta o conteudo
    seguinte ate o proximo ``<h3>`` (irmaos OU descendentes diretos do mesmo
    bloco).
    """
    info = soup.select_one(".info")
    if info is None:
        return None

    target = label.lower()
    # Iteramos descendentes em ordem documental pra lidar tanto com o caso
    # "header e valor irmaos" quanto "agrupados em <div>"
    capture = False
    parts: list[str] = []
    for el in info.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name == "h3":
            if capture:
                break
            if target in el.get_text(strip=True).lower():
                capture = True
            continue
        # Quando capturando, pega o texto dos <a> (geralmente sao eles que
        # carregam o valor); fallback para texto direto.
        if capture and el.name == "a":
            text = el.get_text(" ", strip=True)
            if text:
                parts.append(text)

    if parts:
        return ", ".join(parts)

    # Fallback: alguns labels (ex: "Status") nao usam <a>. Pega o texto cru
    # do irmao seguinte ao <h3>.
    for h3 in info.find_all("h3"):
        if target in h3.get_text(strip=True).lower():
            sib_text = " ".join(
                s.strip() if isinstance(s, str) else s.get_text(" ", strip=True)
                for s in h3.next_siblings
                if (isinstance(s, str) and s.strip())
                or (isinstance(s, Tag) and s.name != "h3")
            ).strip()
            return sib_text or None
    return None


def _extract_cover(soup: BeautifulSoup, base_url: str) -> str | None:
    img = soup.select_one(".book img[src]")
    if img and img.get("src"):
        return urljoin(base_url, img["src"])
    # Fallback: og:image
    meta = soup.select_one('meta[property="og:image"]')
    if meta and meta.get("content"):
        return urljoin(base_url, meta["content"])
    return None


def _extract_description(soup: BeautifulSoup) -> str | None:
    el = soup.select_one(".desc-text")
    return el.get_text("\n", strip=True) or None if el else None


def _detect_last_page(soup: BeautifulSoup) -> int:
    """Le ``ul.pagination`` e descobre o maior numero de pagina.

    Robusto a mudancas de markup: varre todos os ``<a href="?page=N">`` e
    pega o maior N. Retorna 1 se nao houver paginacao (novel curta).
    """
    max_page = 1
    for a in soup.select(".pagination a[href]"):
        m = _PAGE_QS_RE.search(a["href"])
        if m:
            n = int(m.group(1))
            if n > max_page:
                max_page = n
    return max_page


def _extract_chapters_from_page(
    soup: BeautifulSoup, page_url: str
) -> list[ChapterRef]:
    """Coleta os ``<a>`` de capitulo da pagina atual.

    O ``index`` sai zerado aqui — eh renumerado 1..N depois que todas as
    paginas forem coletadas.
    """
    refs: list[ChapterRef] = []
    for a in soup.select("ul.list-chapter li a[href]"):
        href = a.get("href")
        title = (a.get("title") or a.get_text(" ", strip=True)).strip()
        if href:
            refs.append(
                ChapterRef(index=0, title=title, url=urljoin(page_url, href))
            )
    return refs
