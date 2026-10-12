"""Adapter para CSNovels (csnovels.com).

Diferente dos outros adapters, aqui NAO se parseia HTML: o site e uma casca
estatica (o mesmo shell de 119KB volta pra qualquer path, inclusive lixo) e o
conteudo entra por JS via duas Netlify Functions publicas, que sao exatamente
as que o front do proprio site chama. Estrutura mapeada em 2026-08-21:

  - ``/getSingleBook?slug=<slug>``  -> JSON
      {"book": {title, slug, description, coverimage, chaptercount,
                start_chapter, end_chapter, missing_index, paid, status,
                category, ...}, "recommendedBooks": [...]}
  - ``/getsinglechapter?slug=<slug>&chapternumber=<n>``  -> JSON
      {chaptercontent, bookname, chapternumber, nextchapternumber,
       previouschapternumber, chaptercount, spanish, portuguese, ...}

Nao ha endpoint de TOC: os capitulos sao numerados de ``start_chapter`` a
``end_chapter``, entao a lista e gerada por range (descontando as lacunas de
``missing_index``).

Dois detalhes que moldam o codigo:

1. ``chaptercontent`` vem em TEXTO PURO (CRLF, zero tags) — nao da pra usar o
   ``default_clean``, que espera HTML. Ver ``clean``.
2. Obras com ``paid: true`` sao fechadas pelo proprio site: o endpoint de
   capitulo devolve 401 "Authentication required". O adapter respeita isso e
   aborta cedo, com mensagem explicita — nao existe tentativa de contornar.
"""

from __future__ import annotations

import json
import re
from html import escape
from urllib.parse import quote, urlparse

from app.logging_conf import get_logger
from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.base import BaseAdapter
from app.scraper.cleaner import is_spam
from app.scraper.errors import FetchError, ParseError

log = get_logger("csnovels")

# /chapter/<slug>/<n> — o numero e a fonte da verdade pro fetch_chapter.
_CHAPTER_PATH = re.compile(r"^/chapter/(?P<slug>[^/]+)/(?P<num>\d+)")
_BOOK_PATH = re.compile(r"^/book/(?P<slug>[^/?#]+)")


class CSNovelsAdapter(BaseAdapter):
    name = "csnovels"
    domains = ["csnovels.com"]

    async def fetch_novel(self, url: str) -> NovelMeta:
        slug = _slug_from_url(url)
        if not slug:
            raise ParseError(f"nao consegui extrair o slug da URL: {url}")

        base = _base(url)
        payload = await self._get_json(f"{base}/getSingleBook?slug={quote(slug)}")
        book = payload.get("book") if isinstance(payload, dict) else None
        if not isinstance(book, dict):
            raise ParseError(f"resposta sem 'book' em /getSingleBook?slug={slug}")

        # O site fecha as obras pagas no servidor (401 no endpoint de capitulo).
        # Melhor falhar aqui, antes de enfileirar 700 downloads que vao dar 401.
        if book.get("paid"):
            raise FetchError(
                f"'{book.get('title') or slug}' e uma obra paga no CSNovels e exige "
                f"login/assinatura — os capitulos voltam 401. Nao da pra capturar."
            )

        chapters = _build_chapter_list(book, base, slug)
        if not chapters:
            raise ParseError(f"nenhum capitulo listado para {slug}")

        meta = NovelMeta(
            title=(book.get("title") or slug).strip(),
            source_url=url,
            slug=slug,
            # A API nao expoe autor em campo nenhum — fica None de proposito.
            author=None,
            cover_url=book.get("coverimage") or None,
            description=(book.get("description") or "").strip() or None,
            chapters=chapters,
        )
        log.info(
            "novel_parsed",
            title=meta.title,
            chapters=len(meta.chapters),
            status=book.get("status"),
            missing=book.get("missing_count") or 0,
        )
        return meta

    async def fetch_chapter(self, ref: ChapterRef) -> ChapterContent:
        m = _CHAPTER_PATH.match(urlparse(ref.url).path)
        if not m:
            raise ParseError(f"URL de capitulo fora do padrao esperado: {ref.url}")
        slug, num = m.group("slug"), m.group("num")

        base = _base(ref.url)
        try:
            data = await self._get_json(
                f"{base}/getsinglechapter?slug={quote(slug)}&chapternumber={num}"
            )
        except FetchError as exc:
            # O site usa os codigos direitinho: 401 = obra paga, 404 = lacuna.
            if exc.status == 401:
                raise FetchError(
                    f"capitulo {num} de '{slug}' exige login (obra paga no CSNovels)",
                    status=401,
                ) from exc
            if exc.status == 404:
                raise FetchError(
                    f"capitulo {num} de '{slug}' nao existe no CSNovels "
                    f"(lacuna na numeracao?)",
                    status=404,
                ) from exc
            raise

        body = data.get("chaptercontent") if isinstance(data, dict) else None
        if not body or not body.strip():
            raise ParseError(f"capitulo {num} de '{slug}' veio vazio")

        return ChapterContent(
            index=ref.index,
            # A API nao manda titulo do capitulo, so o numero — mantemos o
            # "Chapter N" gerado na TOC, que e o que o parse_chapter_number le.
            title=ref.title or f"Chapter {num}",
            html=self.clean(body),
            url=ref.url,
        )

    def clean(self, raw_text: str) -> str:
        """Texto puro -> ``<p>``.

        Sobrescreve o ``default_clean`` (que espera HTML) de proposito: jogar
        texto cru no BeautifulSoup faria um ``<`` legitimo da prosa virar tag e
        sumir com o resto da linha. Aqui cada linha nao-vazia vira um paragrafo,
        escapado, reusando so o filtro de spam do cleaner.
        """
        paragraphs = [
            line
            for line in (ln.strip() for ln in raw_text.replace("\r\n", "\n").split("\n"))
            if line and not is_spam(line)
        ]
        return "\n".join(f"<p>{escape(p)}</p>" for p in paragraphs)

    # ------------------------------------------------------------------ helpers
    async def _get_json(self, url: str) -> dict:
        # Os endpoints respondem `content-type: text/plain`, entao o parse do
        # JSON e na mao mesmo.
        raw = await self.client.get_text(url)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ParseError(f"resposta nao-JSON em {url}: {exc}") from exc


def _build_chapter_list(book: dict, base: str, slug: str) -> list[ChapterRef]:
    """Gera a TOC por range — o site nao tem endpoint de indice."""
    start = _as_int(book.get("start_chapter")) or 1
    end = _as_int(book.get("end_chapter")) or _as_int(book.get("chaptercount")) or 0
    if end < start:
        return []

    missing = _missing_set(book.get("missing_index"))
    refs: list[ChapterRef] = []
    for n in range(start, end + 1):
        if n in missing:
            continue
        refs.append(
            ChapterRef(
                index=len(refs) + 1,
                # "Chapter N" e o formato que o parse_chapter_number entende —
                # e o que casa esse cap com o mesmo cap em outro mirror.
                title=f"Chapter {n}",
                url=f"{base}/chapter/{slug}/{n}",
            )
        )
    return refs


def _missing_set(raw) -> set[int]:
    """``missing_index`` vem como None, lista ou CSV — normaliza pra set."""
    if raw is None:
        return set()
    if isinstance(raw, (list, tuple)):
        return {n for n in (_as_int(v) for v in raw) if n is not None}
    if isinstance(raw, str):
        return {int(n) for n in re.findall(r"\d+", raw)}
    return set()


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _base(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _slug_from_url(url: str) -> str | None:
    """Aceita /book/<slug> e /chapter/<slug>/<n> (query/fragmento ignorados)."""
    path = urlparse(url).path
    for pattern in (_BOOK_PATH, _CHAPTER_PATH):
        m = pattern.match(path)
        if m:
            return m.group("slug")
    return None
