"""Geracao de arquivos EPUB com ebooklib.

O builder e puro: recebe metadados + capitulos ja limpos (+ bytes da capa) e
escreve o .epub. Nao faz rede nem toca no cache — quem orquestra passa tudo
pronto. Assim regerar o EPUB a partir do cache nao re-baixa nada.

Notas sobre o ebooklib:
  - ``EpubHtml.content`` NAO pode ter declaracao ``<?xml ...?>``: o lxml recusa
    string unicode com encoding declarado e o ebooklib devolve corpo vazio.
  - O ebooklib reconstroi o ``<head>`` (titulo + links). Para o CSS valer e
    preciso ``item.add_item(css)``, nao um ``<link>`` escrito no content.
  - ``set_cover(create_page=True)`` gera uma pagina de capa com corpo vazio que
    quebra a geracao do nav; por isso usamos ``create_page=False`` + pagina
    manual.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

from ebooklib import epub
from slugify import slugify

from app.logging_conf import get_logger
from app.models import ChapterContent, NovelMeta

# Tira o prefixo "Capítulo N / Chapter N / Cap. N" do início do título — o EPUB já
# mostra o número da posição ao lado, então "02 Capítulo 1 Prólogo" vira "02 Prólogo".
# Só o prefixo INICIAL é removido (números no fim do nome, ex: "...Magia Falsa 2",
# ficam). Se sobrar vazio (título era só "Capítulo 1"), mantém o original.
_CHAPTER_PREFIX_RE = re.compile(
    r"^\s*(?:cap[íi]tulo|chapter|cap|ch)\.?\s*-?\d+\s*[:.\-–—)]?\s*",
    re.IGNORECASE,
)


def clean_chapter_title(title: str) -> str:
    cleaned = _CHAPTER_PREFIX_RE.sub("", title).strip()
    return cleaned or title.strip()


# Captura o numero do capitulo do prefixo (ex: "Capítulo 24 ..." -> 24). Usado pra
# montar o cabecalho da pagina ("Capítulo 24" em cima + nome embaixo).
_CHAPTER_NUM_RE = re.compile(r"^\s*(?:cap[íi]tulo|chapter|cap|ch)\.?\s*(-?\d+)", re.IGNORECASE)


def chapter_number(title: str) -> int | None:
    m = _CHAPTER_NUM_RE.match(title)
    return int(m.group(1)) if m else None


def _chapter_header(raw_title: str, language: str) -> str:
    """Cabecalho da pagina do capitulo: 'Capítulo N' (se houver numero) + nome.
    Sem numero parseavel → so o nome. Titulo so-prefixo → so o rotulo."""
    clean = clean_chapter_title(raw_title)
    num = chapter_number(raw_title)
    label = "Capítulo" if (language or "").lower().startswith("pt") else "Chapter"
    # Tem numero E um nome separado do prefixo → eyebrow + titulo.
    if num is not None and clean != raw_title.strip():
        return f'<p class="chapter-eyebrow">{label} {num}</p><h2>{escape(clean)}</h2>'
    return f"<h2>{escape(clean)}</h2>"

log = get_logger("epub")

_CSS = """\
body { font-family: serif; line-height: 1.6; margin: 0 5%; }
h2 { text-align: left; margin: 0.2em 0 0.8em; font-size: 1.3em; }
.chapter-eyebrow { text-align: left; text-transform: uppercase; letter-spacing: 0.12em;
  font-size: 0.78em; color: #888; margin: 1.4em 0 0; text-indent: 0; }
p { margin: 0 0 0.8em; text-indent: 1.5em; }
img.cover { max-width: 100%; height: auto; }
nav.toc h2 { text-align: center; margin: 2em 0 1.5em; font-size: 1.4em; }
nav.toc ol { list-style: none; padding: 0; }
nav.toc li { margin: 0.6em 0; padding: 0.3em 0; border-bottom: 1px dotted #ccc; }
nav.toc li a { text-decoration: none; color: inherit; display: flex; justify-content: space-between; gap: 1em; }
nav.toc li a .num { color: #888; font-variant-numeric: tabular-nums; flex-shrink: 0; }
nav.toc li a .title { flex: 1; }
"""

_CHAPTER = '<html xmlns="http://www.w3.org/1999/xhtml"><body>{header}\n{body}</body></html>'
_COVER = (
    '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
    '<div style="text-align:center;"><img class="cover" src="{filename}" alt="Cover"/></div>'
    "</body></html>"
)
# Pagina de sumario visivel (clicavel). epub:type="toc" deixa o Kindle/iBooks
# reconhecer como o TOC oficial alem do nav.xhtml. <ol> ordenada com numero +
# titulo. Sem "pagina" porque EPUB e reflowable (location/% e gerado pelo
# leitor); o numero do cap e a referencia editorial estavel.
_TOC_PAGE = (
    '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
    '<body>'
    '<nav epub:type="toc" class="toc" id="toc">'
    '<h2>Sumário</h2>'
    '<ol>{items}</ol>'
    '</nav>'
    '</body></html>'
)
_TOC_ITEM = (
    '<li><a href="{href}">'
    '<span class="num">{num}</span>'
    '<span class="title">{title}</span>'
    '</a></li>'
)


def build_epub(
    meta: NovelMeta,
    chapters: list[ChapterContent],
    output_path: str | Path,
    *,
    cover_bytes: bytes | None = None,
    language: str = "en",
    epub_title: str | None = None,
) -> Path:
    """Monta e escreve o EPUB. Retorna o caminho final.

    ``epub_title``: se setado, vira o titulo da obra (ex: "Volume 1 — O Sistema
    Vampirico"). A novel original entra como ``dc:source`` + calibre series.
    """
    if not chapters:
        raise ValueError("nenhum capitulo para gerar o EPUB")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    title = epub_title or meta.title

    book = epub.EpubBook()
    # ID estavel por (URL + titulo) p/ Kindle distinguir volumes da mesma novel.
    book.set_identifier(f"{meta.source_url}#{slugify(title)}" if epub_title else (meta.source_url or title))
    book.set_title(title)
    book.set_language(language)
    if meta.author:
        book.add_author(meta.author)
    if meta.description:
        book.add_metadata("DC", "description", meta.description)
    book.add_metadata("DC", "source", meta.source_url)
    # Quando ha titulo de volume, registra a novel como serie (Kindle/Calibre)
    if epub_title:
        book.add_metadata(
            None,
            "meta",
            "",
            {"name": "calibre:series", "content": meta.title},
        )

    css = epub.EpubItem(
        uid="style_main",
        file_name="style/main.css",
        media_type="text/css",
        content=_CSS,
    )
    book.add_item(css)

    # --- Capa: imagem (com property cover-image via set_cover) + pagina manual ---
    cover_page: epub.EpubHtml | None = None
    if cover_bytes:
        # Detecta PNG/JPEG/GIF pelos magic bytes pro mime correto.
        if cover_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            cover_filename = "cover.png"
        elif cover_bytes[:6] in (b"GIF87a", b"GIF89a"):
            cover_filename = "cover.gif"
        else:
            cover_filename = "cover.jpg"  # JPEG ou fallback
        book.set_cover(cover_filename, cover_bytes, create_page=False)
        cover_page = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang=language)
        cover_page.content = _COVER.format(filename=cover_filename)
        cover_page.add_item(css)
        book.add_item(cover_page)

    # --- Capitulos (ordenados por indice) ---
    epub_chapters: list[epub.EpubHtml] = []
    for ch in sorted(chapters, key=lambda c: c.index):
        ctitle = clean_chapter_title(ch.title)
        item = epub.EpubHtml(
            title=ctitle,
            file_name=f"chap_{ch.index:05d}.xhtml",
            lang=language,
        )
        item.content = _CHAPTER.format(
            header=_chapter_header(ch.title, language), body=ch.html
        )
        item.add_item(css)
        book.add_item(item)
        epub_chapters.append(item)

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Pagina de TOC visivel — so vale a pena quando ha multiplos capitulos.
    # Pra 1 cap o sumario seria so um item que ja esta no nav nativo.
    toc_page: epub.EpubHtml | None = None
    if len(epub_chapters) > 1:
        items_html = "".join(
            _TOC_ITEM.format(
                href=item.file_name,
                num=f"{ch.index:02d}",
                title=escape(clean_chapter_title(ch.title)),
            )
            for ch, item in zip(sorted(chapters, key=lambda c: c.index), epub_chapters)
        )
        toc_page = epub.EpubHtml(
            title="Sumário", file_name="toc.xhtml", lang=language
        )
        toc_page.content = _TOC_PAGE.format(items=items_html)
        toc_page.add_item(css)
        book.add_item(toc_page)

    # Spine: capa → sumario visivel → capitulos. O nav.xhtml NAO entra no spine
    # (era pagina dupla com nosso toc_page); fica so como nav doc estrutural do
    # EPUB3 (acessivel via menu "Ir para → Sumario" do Kindle/iBooks). Quando
    # nao ha toc_page (1 cap), tambem nao precisa do nav visivel — leitor pula
    # direto pro cap unico.
    spine: list = []
    if cover_page is not None:
        spine.append(cover_page)
    if toc_page is not None:
        spine.append(toc_page)
    spine.extend(epub_chapters)
    book.spine = spine

    epub.write_epub(str(output_path), book)
    log.info(
        "epub_built",
        path=str(output_path),
        chapters=len(epub_chapters),
        cover=bool(cover_bytes),
    )
    return output_path
