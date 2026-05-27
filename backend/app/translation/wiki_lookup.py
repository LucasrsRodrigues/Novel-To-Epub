"""Lookup leve em wikis Fandom (MediaWiki API).

Pegamos APENAS o trecho de introducao (`exintro&explaintext`) — costuma trazer
o essencial (papel, gênero implícito, raça/facção) sem revelar arcos futuros.
Tudo eh cacheado em ``wiki_lookups`` por novel.
"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from urllib.parse import quote

from app.db import models as orm
from app.db.database import get_session, init_db
from app.logging_conf import get_logger

log = get_logger("wiki")

_UA = "NovelToEPUB/0.1 (personal use)"


class WikiClient:
    """Descobre + consulta a wiki Fandom de uma novel."""

    def __init__(self, *, timeout: float = 6.0) -> None:
        init_db()
        self.timeout = timeout

    # ----- descoberta -----
    async def discover(self, novel_id: int, novel_slug: str) -> str | None:
        """Detecta a URL da wiki para a novel. Cacheia em ``novels.wiki_url/status``."""
        with get_session() as s:
            novel = s.get(orm.Novel, novel_id)
            if novel is None:
                return None
            if novel.wiki_status != "unknown":
                return novel.wiki_url  # ja tentamos antes (detected ou none)

        # Tenta 2 variantes do subdominio: com e sem hifens.
        candidates = {novel_slug, novel_slug.replace("-", "")}
        async with httpx.AsyncClient(
            timeout=self.timeout, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            for sub in candidates:
                url = f"https://{sub}.fandom.com"
                try:
                    r = await client.get(
                        f"{url}/api.php",
                        params={"action": "query", "meta": "siteinfo", "format": "json"},
                    )
                    if r.status_code == 200 and "query" in r.json():
                        _persist_wiki(novel_id, url, "detected")
                        log.info("wiki_detected", novel_slug=novel_slug, url=url)
                        return url
                except Exception as exc:
                    log.debug("wiki_probe_failed", subdomain=sub, error=str(exc))

        _persist_wiki(novel_id, None, "none")
        log.info("wiki_not_found", novel_slug=novel_slug)
        return None

    # ----- lookup -----
    async def lookup(self, novel_id: int, novel_slug: str, term: str) -> dict:
        """Retorna ``{found, summary, source_url}``. Cacheia em ``wiki_lookups``."""
        # 1) cache
        cached = _cached_lookup(novel_id, term)
        if cached is not None:
            return cached

        # 2) descobre wiki
        wiki_url = await self.discover(novel_id, novel_slug)
        if not wiki_url:
            result = {"found": False, "summary": None, "source_url": None}
            _save_lookup(novel_id, term, result)
            return result

        # 3) opensearch + extracts
        async with httpx.AsyncClient(
            timeout=self.timeout, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            try:
                osr = await client.get(
                    f"{wiki_url}/api.php",
                    params={
                        "action": "opensearch",
                        "search": term,
                        "limit": "1",
                        "namespace": "0",
                        "format": "json",
                    },
                )
                osr.raise_for_status()
                data = osr.json()
                titles = data[1] if len(data) > 1 else []
                urls = data[3] if len(data) > 3 else []
                if not titles:
                    result = {"found": False, "summary": None, "source_url": None}
                    _save_lookup(novel_id, term, result)
                    return result

                title = titles[0]
                source_url = urls[0] if urls else f"{wiki_url}/wiki/{quote(title)}"

                # action=parse devolve o HTML renderizado da pagina. O extension
                # TextExtracts nem sempre esta instalado em Fandom wikis, e quando
                # esta, paginas com so infobox voltam vazias. HTML + BS4 eh confiavel.
                ext = await client.get(
                    f"{wiki_url}/api.php",
                    params={
                        "action": "parse",
                        "page": title,
                        "prop": "text",
                        "redirects": "1",
                        "format": "json",
                    },
                )
                ext.raise_for_status()
                body = ext.json()
                # `or {}` em cada passo: a chave pode existir com valor null
                parse_obj = body.get("parse") or {}
                text_obj = parse_obj.get("text") or {}
                # formatversion=1 -> dict {"*": "..."}; formatversion=2 -> string direta
                html_text = (
                    text_obj if isinstance(text_obj, str) else text_obj.get("*", "")
                ) or ""
                summary = _extract_prose(html_text)

                result = {
                    "found": bool(summary),
                    "summary": summary or None,
                    "source_url": source_url,
                }
                _save_lookup(novel_id, term, result)
                log.info("wiki_lookup", term=term, found=result["found"], chars=len(summary))
                return result
            except Exception as exc:
                import traceback
                log.warning(
                    "wiki_lookup_error",
                    term=term,
                    error=str(exc),
                    tb=traceback.format_exc().splitlines()[-4:],
                )
                result = {"found": False, "summary": None, "source_url": None}
                # Nao cacheia erros — talvez seja transitorio.
                return result


def _extract_prose(html: str, max_chars: int = 800) -> str:
    """Tira <aside>/infobox/<table>/<style>/<script> e devolve os primeiros <p> reais."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["aside", "table", "style", "script", "figure", "nav"]):
        tag.decompose()
    # Fandom usa "portable-infobox" / "infobox" como classes em div tambem.
    # Selectors CSS evitam o bug do BS4+lxml onde find_all(True) traz nodes
    # com attrs=None.
    for sel in (".infobox", ".portable-infobox", ".navbox", ".toc", ".thumbnail"):
        for el in soup.select(sel):
            el.decompose()

    chunks: list[str] = []
    total = 0
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) < 30:  # pula vazios e linhas curtas (geralmente lixo)
            continue
        chunks.append(text)
        total += len(text)
        if total >= max_chars:
            break
    return _clip(" ".join(chunks), max_chars)


def _clip(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[: n - 1].rsplit(" ", 1)[0] + "…"


def _persist_wiki(novel_id: int, wiki_url: str | None, status: str) -> None:
    with get_session() as s:
        novel = s.get(orm.Novel, novel_id)
        if novel is None:
            return
        novel.wiki_url = wiki_url
        novel.wiki_status = status
        s.commit()


def _cached_lookup(novel_id: int, term: str) -> dict | None:
    with get_session() as s:
        row = s.scalar(
            select(orm.WikiLookup).where(
                orm.WikiLookup.novel_id == novel_id, orm.WikiLookup.term == term
            )
        )
        if row is None:
            return None
        return {"found": row.found, "summary": row.summary, "source_url": row.source_url}


def _save_lookup(novel_id: int, term: str, result: dict) -> None:
    with get_session() as s:
        row = s.scalar(
            select(orm.WikiLookup).where(
                orm.WikiLookup.novel_id == novel_id, orm.WikiLookup.term == term
            )
        )
        if row is None:
            row = orm.WikiLookup(novel_id=novel_id, term=term)
            s.add(row)
        row.found = bool(result["found"])
        row.summary = result.get("summary")
        row.source_url = result.get("source_url")
        s.commit()
