"""Adapter WuxiaWorldEU com paginas falsas no formato do site (sem rede)."""

import asyncio
import json

import pytest

from app.scraper.adapters.wuxiaworld_eu import WuxiaWorldEUAdapter
from app.scraper.errors import ParseError
from app.scraper.registry import registry


def _page(page_props: dict) -> str:
    data = {"props": {"pageProps": page_props}, "page": "/x"}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


NOVEL = {
    "title": "Magic Industry Empire", "description": "Engenheiro em outro mundo.",
    "status": "COMPLETED", "author": {"name": "Eight O'Clock At Night"},
    "coverOriginal": "original/mie_cover.jpg", "firstChapterNumber": "1", "chapterCount": "4",
}


def _toc(items, page, pages):
    return {"items": items, "range": {"page": page},
            "ranges": [{"page": p, "from": 0, "to": 0} for p in range(1, pages + 1)]}


PAGES = {
    "https://wuxiaworld.eu/novel-detail/mie": _page({"novel": NOVEL, "toc": _toc(
        [{"number": 1, "title": "Volume 1 Chapter 1 - Applicant"},
         {"number": 2, "title": "Volume 1 Chapter 2 - Exam"}], 1, 2)}),
    "https://wuxiaworld.eu/novel/mie?page=2": _page({"novel": NOVEL, "toc": _toc(
        [{"number": 3, "title": "Volume 2 Chapter 1 - Duke"},
         {"number": 4, "title": "Volume 2 Chapter 2 - End"}], 2, 2)}),
    "https://wuxiaworld.eu/chapter/mie-3": _page({"data": {"chapter": {
        "number": 3, "title": "Volume 2 Chapter 1 - Duke",
        "paragraphs": ["Volume 2 Chapter 1 Duke", "“<You have learned Fireball>”", "  ", "Fim."]}}}),
}


class FakeClient:
    def __init__(self):
        self.calls = []

    async def get_text(self, url, *, throttle=True):
        self.calls.append((url, throttle))
        if url not in PAGES:
            raise AssertionError(f"url inesperada: {url}")
        return PAGES[url]


def test_fetch_novel_reads_all_toc_pages_with_volumes_and_clean_titles():
    client = FakeClient()
    a = WuxiaWorldEUAdapter(client)
    progress = []
    a.on_meta_progress = lambda d, t, label: progress.append((d, t))
    meta = asyncio.run(a.fetch_novel("https://wuxiaworld.eu/novel-detail/mie"))
    assert meta.title == "Magic Industry Empire" and meta.author == "Eight O'Clock At Night"
    assert meta.cover_url == "https://cdn.wuxiaworld.eu/original/mie_cover.jpg"
    assert [(c.index, c.title, c.volume_label) for c in meta.chapters] == [
        (1, "Chapter 1 - Applicant", "Volume 1"), (2, "Chapter 2 - Exam", "Volume 1"),
        (3, "Chapter 1 - Duke", "Volume 2"), (4, "Chapter 2 - End", "Volume 2"),
    ]
    assert meta.chapters[2].url == "https://wuxiaworld.eu/chapter/mie-3"
    assert progress[-1] == (2, 2)
    assert ("https://wuxiaworld.eu/novel/mie?page=2", False) in client.calls  # TOC sem throttle


def test_fetch_chapter_escapes_text_and_drops_repeated_title():
    a = WuxiaWorldEUAdapter(FakeClient())
    meta = asyncio.run(a.fetch_novel("https://wuxiaworld.eu/novel-detail/mie"))
    ch = asyncio.run(a.fetch_chapter(meta.chapters[2]))
    assert ch.title == "Chapter 1 - Duke" and ch.index == 3
    assert ch.html == "<p>“&lt;You have learned Fireball&gt;”</p>\n<p>Fim.</p>"


def test_registry_resolves_novel_and_chapter_urls_but_not_wuxiaworld_com():
    for url in ("https://wuxiaworld.eu/novel-detail/mie", "https://wuxiaworld.eu/novel/mie?page=3",
                "https://www.wuxiaworld.eu/chapter/mie-12"):
        assert registry.resolve(url, FakeClient()).name == "wuxiaworld_eu"
    assert not registry.supports("https://www.wuxiaworld.com/novel/martial-world")


def test_page_without_next_data_is_parse_error():
    PAGES["https://wuxiaworld.eu/novel-detail/quebrado"] = "<html>Just a page</html>"
    with pytest.raises(ParseError, match="__NEXT_DATA__"):
        asyncio.run(WuxiaWorldEUAdapter(FakeClient()).fetch_novel("https://wuxiaworld.eu/novel-detail/quebrado"))
