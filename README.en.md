# Novel-to-EPUB

> A web novel scraper that builds full `.epub` files — with AI translation,
> AI-generated covers, Kindle delivery and a desktop UI.

🇬🇧 English · [🇧🇷 Português (BR)](README.md) (full version)

Paste a novel URL, pick a chapter range, and the app downloads, optionally
translates, optionally generates a cover, builds the EPUB, and (if you want)
emails it straight to your Kindle. Everything runs locally. The SQLite cache
makes sure nothing is downloaded twice.

**Stack:** Python 3.10+ (FastAPI + Typer CLI) · Electron 39 + React 19 + Tailwind 4 · SQLite

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Node](https://img.shields.io/badge/node-18%2B-green)

![Library](docs/screenshots/tela-biblioteca.png)

---

> ⚠️ **Legal — personal use only.**
> This project is an **offline reading tool**. Web novels are typically
> copyrighted and most sites prohibit scraping in their ToS. **You are
> responsible** for: (a) respecting each site's ToS, (b) not redistributing
> the generated EPUBs, (c) supporting the original author whenever possible
> (Patreon, official books etc). The project **does not host content** —
> it just automates a human reader doing what they'd do manually.

---

## Why?

I read web novels (Shadow Slave, Lord of the Mysteries, Supreme Magus) and
wanted to read them on Kindle. Stitching together caps with ad-laden
chapter pages was painful. So: pick range → click → EPUB.

It does PT-BR translation via a multi-provider AI cascade (Groq → OpenRouter →
Cerebras → Gemini, with retry/fallback) and keeps proper nouns consistent
through an auto-built glossary across hundreds of chapters.

---

## Features

- **Multi-site** via Strategy pattern + auto-discovery — adding a new site is
  one file in `backend/app/scraper/adapters/`.
- **SQLite chapter cache** — re-running a novel hits zero network.
- **Full EPUB** — cover, metadata, navigable TOC, paginated volumes.
- **AI translation cascade** with auto glossary persistence — "Yun Che" stays
  "Yun Che" across 1000 caps.
- **AI cover** (Gemini Image) — visual brief from first chapters + editorial
  typography composited via Pillow.
- **Kindle delivery** via SMTP.
- **Concurrent TOC pagination** for adapters with paginated chapter lists
  (NovelFull has 66 pages — sequential would take ~130s, concurrent does it
  in ~5s).

---

## Supported sites

| Site         | Domains                                                       | Status       |
|--------------|---------------------------------------------------------------|--------------|
| NovelBin     | `novelbin.com`, `novelbin.me`, `novelbin.net`, `.org`, `.io`  | ✅ Ready    |
| NovelMania   | `novelmania.com.br` (PT-BR native, skips translation)         | ✅ Ready    |
| NovelFull    | `novelfull.net`                                               | ✅ Ready    |

Don't see your site? Open an
[adapter request](.github/ISSUE_TEMPLATE/adapter_request.md) — or write the
adapter yourself, see below.

---

## Quickstart (no API keys, ~30s)

EPUB in 3 commands, no translation:

```bash
git clone https://github.com/LucasrsRodrigues/Novel-To-Epub.git
cd Novel-To-Epub
make install
make download URL=https://novelbin.com/b/lord-of-mysteries START=1 END=10
```

EPUB lands in `backend/data/epubs/`. For the GUI + translation + Kindle
delivery, see the [full PT-BR README](README.md#instalação).

---

## Download (macOS binaries)

Grab the `.dmg` from
[Releases](https://github.com/LucasrsRodrigues/Novel-To-Epub/releases).

> ⚠️ The build is **not signed nor notarized** (Apple charges $99/yr).
> macOS will say "Apple could not verify". Right-click the `.app` → **Open**,
> confirm once, and you're set. Or: `xattr -dr com.apple.quarantine "/Applications/Novel to EPUB.app"`.

Verify the SHA256 against the release page.

Linux/Windows: source-only for now — `make build-electron` works.

---

## Add a new site adapter

The registry auto-discovers adapters — just create one file.

**1.** Create `backend/app/scraper/adapters/your_site.py`:

```python
from __future__ import annotations

from bs4 import BeautifulSoup

from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.base import BaseAdapter


class YourSiteAdapter(BaseAdapter):
    name = "your_site"
    domains = ["your-site.com"]

    async def fetch_novel(self, url: str) -> NovelMeta:
        html = await self.client.get_text(url)
        soup = BeautifulSoup(html, "lxml")

        chapters = [
            ChapterRef(
                index=i,
                title=a.get_text(strip=True),
                url=a["href"],
                volume_label=None,
            )
            for i, a in enumerate(soup.select(".chapter-list a"), start=1)
        ]

        return NovelMeta(
            title=soup.select_one("h1.title").get_text(strip=True),
            source_url=url,
            slug="novel-slug",
            author=soup.select_one(".author").get_text(strip=True),
            cover_url=soup.select_one(".cover img")["src"],
            description="",
            chapters=chapters,
        )

    async def fetch_chapter(self, ref: ChapterRef) -> ChapterContent:
        html = await self.client.get_text(ref.url)
        soup = BeautifulSoup(html, "lxml")
        return ChapterContent(
            index=ref.index,
            title=ref.title,
            html=self.clean(str(soup.select_one(".chapter-content"))),
            url=ref.url,
        )
```

**2.** Add `from . import your_site` to
[`backend/app/scraper/adapters/__init__.py`](backend/app/scraper/adapters/__init__.py).
This is **required** — PyInstaller only follows static imports, so without
this the bundled `.app` silently can't find your adapter (works fine in dev
because `pkgutil.iter_modules` scans the filesystem).

**3.** Test it:

```bash
make sites                                    # confirms registration
make detect URL=https://your-site.com/novel   # confirms URL matching
make download URL=... START=1 END=5 LOG=DEBUG
```

**4.** If the TOC is paginated (>20 pages), report progress so the UI shows
"page X/Y" instead of staring at 0%. See
[novellfull.py](backend/app/scraper/adapters/novellfull.py) for a
concurrent pagination reference (uses `asyncio.Semaphore` + `throttle=False`).

Full contract: [`backend/app/scraper/base.py`](backend/app/scraper/base.py).

---

## Architecture

```
┌──────────────┐  HTTP/WS   ┌────────────────────────┐
│ Electron UI  │ ─────────▶ │ FastAPI (REST + WS)    │
└──────────────┘            └───────────┬────────────┘
                                        │ enqueue
                                        ▼
                            ┌────────────────────────┐
                            │ JobManager (async)     │
                            └───────────┬────────────┘
                                        ▼
                            ┌────────────────────────┐
                            │ orchestrator           │
                            │  download_to_epub()    │
                            └───────────┬────────────┘
              ┌─────────────────────────┼─────────────────────────┐
              ▼                         ▼                         ▼
       ┌─────────────┐          ┌──────────────┐         ┌────────────────┐
       │ scraper     │          │ translation  │         │ image_gen      │
       │ (Strategy)  │          │ (cascade)    │         │ (Gemini)       │
       └──────┬──────┘          └──────┬───────┘         └────────┬───────┘
              ▼                         ▼                         ▼
       ┌─────────────────────────────────────────────────────────────────┐
       │ SQLite (cache, glossary, settings, usage, volumes, covers)      │
       └─────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                            ┌────────────────────────┐
                            │ epub/builder           │
                            │ → .epub                │
                            └────────────────────────┘
```

---

## Contributing

PRs and issues welcome. Best places to start:

- **New site adapter** (see above) — highest leverage
- **Embed TTFs** for cross-platform cover typography
- **Adapter tests** (HTML fixtures + pytest)
- **UI translations**

📋 [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, acceptance criteria,
release process for maintainers.

🔒 Security: [SECURITY.md](SECURITY.md).

📝 Changes: [CHANGELOG.md](CHANGELOG.md).

---

## License

[MIT](LICENSE) © 2026 Lucas Rodrigues

The full Portuguese README has additional sections (interactive menu,
detailed API reference, environment variables, project structure, Make
targets) — [check it out](README.md).
