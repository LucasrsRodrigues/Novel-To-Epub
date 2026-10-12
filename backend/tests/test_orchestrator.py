"""download_to_epub ponta a ponta com adapters falsos e SQLite temporario."""

import asyncio
import re
import zipfile

import pytest

import app.orchestrator as orch
from app.db.cache import ChapterCache
from app.db.mirror_store import MirrorStore
from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.adapters.csnovels import _build_chapter_list


def _epub_chapters(path) -> list[str]:
    z = zipfile.ZipFile(path)
    found = []
    for name in z.namelist():
        m = re.search(rb"corpo (Chapter \d+)", z.read(name))
        if m:
            found.append(m.group(1).decode())
    return sorted(found, key=lambda t: int(t.split()[-1]))


class _Registry:
    def __init__(self, by_prefix):
        self.by_prefix = by_prefix

    def resolve(self, url, client):
        for prefix, adapter in self.by_prefix.items():
            if url.startswith(prefix):
                return adapter
        raise AssertionError(f"url inesperada: {url}")


def test_csnovels_gap_filled_later_keeps_cached_chapters_aligned(monkeypatch):
    state = {"missing": "3"}

    class CSNovels:
        name = "csnovels"

        async def fetch_novel(self, url):
            ch = _build_chapter_list(
                {"start_chapter": 1, "end_chapter": 6, "missing_index": state["missing"]},
                "https://c", "s",
            )
            return NovelMeta(title="Gap", source_url=url, slug="gap", chapters=ch)

        async def fetch_chapter(self, ref):
            return ChapterContent(index=ref.index, title=ref.title,
                                  html=f"<p>corpo {ref.title}</p>", url=ref.url)

    monkeypatch.setattr(orch, "registry", _Registry({"https://c": CSNovels()}))

    p1 = asyncio.run(orch.download_to_epub("https://c/book/s", with_cover=False))
    assert _epub_chapters(p1) == [f"Chapter {n}" for n in (1, 2, 4, 5, 6)]
    state["missing"] = None  # o site preencheu a lacuna
    p2 = asyncio.run(orch.download_to_epub("https://c/book/s", with_cover=False))
    assert _epub_chapters(p2) == [f"Chapter {n}" for n in range(1, 7)]


def test_csnovels_prologue_is_kept():
    refs = _build_chapter_list({"start_chapter": 0, "end_chapter": 2}, "https://c", "s")
    assert [(r.index, r.title) for r in refs] == [(1, "Chapter 0"), (2, "Chapter 1"), (3, "Chapter 2")]


def test_unavailable_mirror_is_not_refetched_for_every_chapter(monkeypatch):
    toc_calls = 0

    class Primary:
        name = "primary"

        async def fetch_novel(self, url):
            refs = [ChapterRef(index=i, title=f"Chapter {i}", url=f"https://p/{i}") for i in range(1, 6)]
            return NovelMeta(title="Mirror", source_url=url, slug="mirror-novel", chapters=refs)

        async def fetch_chapter(self, ref):
            raise RuntimeError("primario fora")

    class DeadMirror:
        name = "dead"

        async def fetch_novel(self, url):
            nonlocal toc_calls
            toc_calls += 1
            raise RuntimeError("mirror bloqueado")

    monkeypatch.setattr(orch, "registry", _Registry({"https://p": Primary(), "https://m": DeadMirror()}))
    novel_id = ChapterCache().upsert_novel(
        "primary", "mirror-novel", NovelMeta(title="Mirror", source_url="https://p", chapters=[])
    )
    MirrorStore().add(novel_id, "dead", "https://m/novel")

    with pytest.raises(Exception):  # nenhum capitulo baixado → volume vazio
        asyncio.run(orch.download_to_epub("https://p/novel", with_cover=False))
    assert toc_calls == 1  # antes: 1 por capitulo que falhou (5)


def test_epub_build_does_not_block_event_loop(monkeypatch):
    """Enquanto o .epub e montado, o loop continua atendendo (WS, outras rotas)."""
    import time

    class Site:
        name = "site"

        async def fetch_novel(self, url):
            refs = [ChapterRef(index=1, title="Chapter 1", url="https://s/1")]
            return NovelMeta(title="Loop", source_url=url, slug="loop", chapters=refs)

        async def fetch_chapter(self, ref):
            return ChapterContent(index=1, title="Chapter 1", html="<p>x</p>", url=ref.url)

    def slow_build(*args, **kwargs):
        time.sleep(0.5)  # simula um volume grande sendo zipado

    monkeypatch.setattr(orch, "registry", _Registry({"https://s": Site()}))
    monkeypatch.setattr(orch, "build_epub", slow_build)

    async def main():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.05)
                ticks += 1

        t = asyncio.create_task(ticker())
        await orch.download_to_epub("https://s/novel", with_cover=False)
        t.cancel()
        return ticks

    assert asyncio.run(main()) >= 5  # bloqueando, seriam ~0 ticks durante os 0,5s
