"""Adapter para NovelMania (novelmania.com.br) — fonte PT-BR nativa.

Por que importa: novel já vem traduzida em português pelo fan-tradutor do site,
então não precisa pagar Gemini/Groq pra traduzir. Custo de tradução = R$ 0.

Estrutura do site (mapeada em 2026-05):
  - Stack: Rails + Bootstrap 4, SSR puro (sem AJAX), Cloudflare como CDN passivo.
  - Pagina da novel: ``/novels/<slug>``
      titulo  -> ``div.novel-info h1``
      autor   -> ``span.authors`` cujo <b> seja "Autor:" (pega texto após)
      capa    -> ``div.novel-img img[src]``
      desc    -> ``div#info div.text`` (sinopse + notas)
      caps    -> ``div#chapters div.card`` (1 card por VOLUME, com <ol> de chapters dentro)
  - Pagina do capitulo: ``/novels/<slug>/capitulos/<chap-slug>``
      titulo  -> ``div#chapter-content > h2``
      corpo   -> ``div#chapter-content > p`` (parar no <hr> + <h6>Notas:</h6>)

A lista de capítulos vem TODA na página da novel (sem paginação) — 1 request HTTP
pega novel + 1900+ capítulos quando aplicavel.

Volumes são preservados no `title` do ChapterRef (formato "Volume N — Cap K: Título")
pra que o usuário tenha contexto editorial. Não há suporte nativo a "selecionar
volume" no DownloadRequest ainda — usuário usa start/end de capítulos normais.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.logging_conf import get_logger
from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.base import BaseAdapter
from app.scraper.errors import ParseError

log = get_logger("novelmania")


class NovelManiaAdapter(BaseAdapter):
    name = "novelmania"
    domains = ["novelmania.com.br"]

    async def fetch_novel(self, url: str) -> NovelMeta:
        soup = BeautifulSoup(await self.client.get_text(url), "lxml")

        title_el = soup.select_one("div.novel-info h1")
        if title_el is None:
            raise ParseError(f"título da novel não encontrado em {url}")
        # Remove o <span class="sigla"> se estiver junto (ex: "Contra os Deuses [WN]")
        for sp in title_el.select("span"):
            sp.extract()
        title = title_el.get_text(" ", strip=True)

        meta = NovelMeta(
            title=title,
            source_url=url,
            slug=_slug_from_url(url),
            author=_extract_authors(soup),
            cover_url=_extract_cover(soup, url),
            description=_extract_description(soup),
            chapters=_extract_chapter_refs(soup, url),
        )
        log.info(
            "novel_parsed",
            title=meta.title, author=meta.author,
            chapters=len(meta.chapters), slug=meta.slug,
        )
        return meta

    async def fetch_chapter(self, ref: ChapterRef) -> ChapterContent:
        soup = BeautifulSoup(await self.client.get_text(ref.url), "lxml")

        content_el = soup.select_one("div#chapter-content")
        if content_el is None:
            raise ParseError(f"conteúdo do capítulo não encontrado em {ref.url}")

        # Título autoritativo lido do <h2> dentro do content (ou ref.title se faltar)
        h2 = content_el.select_one("h2")
        title = h2.get_text(" ", strip=True) if h2 else ref.title

        # Limpa nós que não fazem parte do texto narrativo
        for tag in content_el.select(
            "div#reactions-component, div.donation-section, script, ins, "
            "div.adsbygoogle, h2, h3, h6"
        ):
            tag.decompose()

        # Pega só os <p> ANTES da seção de notas (separada por <hr>)
        body_paragraphs: list[str] = []
        for child in content_el.children:
            if not isinstance(child, Tag):
                continue
            if child.name == "hr":
                break  # Tudo depois é nota de rodapé do tradutor
            if child.name == "p":
                text = child.get_text(" ", strip=True)
                if text:
                    body_paragraphs.append(f"<p>{_escape_html(text)}</p>")

        if not body_paragraphs:
            raise ParseError(f"nenhum parágrafo encontrado em {ref.url}")

        html = "\n".join(body_paragraphs)
        return ChapterContent(
            index=ref.index, title=title, html=html, url=ref.url,
        )

    # NovelMania serve PT-BR limpo; clean default basta (escape de entities já feito).
    # Não override `clean` — o conteúdo extraído acima já é HTML válido.


# --------------------------- helpers de parse ------------------------------


def _slug_from_url(url: str) -> str:
    """Extrai o slug da novel: /novels/<slug>(/...) → <slug>."""
    path = urlparse(url).path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if "novels" in parts:
        idx = parts.index("novels")
        if len(parts) > idx + 1:
            return parts[idx + 1]
    return parts[-1] if parts else "novel"


def _extract_authors(soup: BeautifulSoup) -> str | None:
    """Pega o texto após <b>Autor:</b> em <span class='authors'>."""
    for span in soup.select("span.authors"):
        b = span.find("b")
        if b and "autor" in b.get_text(strip=True).lower():
            # Remove o <b> e pega o resto do texto
            b.extract()
            text = span.get_text(" ", strip=True)
            return text or None
    return None


def _extract_cover(soup: BeautifulSoup, base_url: str) -> str | None:
    img = soup.select_one("div.novel-img img[src]")
    if not img:
        return None
    src = img["src"]
    # URLs do NovelMania vêm absolutas, mas defensivamente resolve relativa
    return urljoin(base_url, src)


def _extract_description(soup: BeautifulSoup) -> str | None:
    """Pega só os <p> da seção Sinopse (entre <h4>Sinopse</h4> e o próximo <h4>)."""
    container = soup.select_one("div#info div.text")
    if container is None:
        meta = soup.select_one('meta[property="og:description"], meta[name="description"]')
        return meta["content"].strip() if meta and meta.get("content") else None

    # Estrutura: <h4>Sinopse</h4> <p>...</p> <p>...</p> <h4>Notas</h4> ...
    # Coletamos <p>s DEPOIS de "Sinopse" e ANTES do próximo header.
    in_synopsis = False
    paragraphs: list[str] = []
    for child in container.children:
        if not isinstance(child, Tag):
            continue
        if child.name in ("h4", "h5", "h6"):
            heading = child.get_text(strip=True).lower()
            if "sinopse" in heading:
                in_synopsis = True
                continue
            if in_synopsis:
                break  # outro header = fim da sinopse
        elif in_synopsis and child.name == "p":
            text = child.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)

    if not paragraphs:
        return None
    return "\n\n".join(paragraphs)


# Regex pra extrair número de capítulo do <strong> do <a>
_CHAP_NUM_RE = re.compile(r"cap[íi]tulo\s+(\d+)", re.IGNORECASE)
_PROLOGO_RE = re.compile(r"pr[óo]logo|prefacio|epilogo", re.IGNORECASE)


def _extract_chapter_refs(soup: BeautifulSoup, base_url: str) -> list[ChapterRef]:
    """Extrai TODA a lista de capítulos do `#chapters` num único pass.

    Estrutura real (descoberto empiricamente, NÃO um card por volume):
      <div#chapters> <div.accordion> <div.card> <div.card-body>
        <ol>
          <li><a><span.sub-vol>Volume 1</span><strong>Prólogo</strong>...</a></li>
          <li><a><span.sub-vol>Volume 19</span><strong>Capítulo 1934</strong>...</a></li>
          ...
        </ol>

    Cada <a> tem o volume real em `<span class="sub-vol">`. O `title` vira
    "Volume N — <título>" pra preservar contexto editorial. `index` é sequencial.
    """
    
    chapters: list[ChapterRef] = []

    # Pega TODOS os <a> de capítulo direto, sem depender de structure por volume
    anchors = soup.select("div#chapters ol li a[href]")

    for i, li_a in enumerate(anchors, start=1):
        href = li_a["href"]

        full_url = urljoin(base_url, href)

        vol_span = li_a.select_one("span.sub-vol")

        strong = li_a.select_one("strong")

        vol_label = vol_span.get_text(" ", strip=True) if vol_span else None

        cap_title_text = (
            strong.get_text(" ", strip=True) if strong
            else li_a.get_text(" ", strip=True)
        )

        title = f"{vol_label} — {cap_title_text}" if vol_label else cap_title_text

        chapters.append(ChapterRef(
            index=i, title=title, url=full_url, volume_label=vol_label,
        ))
        
    return chapters


def _escape_html(text: str) -> str:
    """Escape mínimo de < > & pra HTML seguro dentro de <p>."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
