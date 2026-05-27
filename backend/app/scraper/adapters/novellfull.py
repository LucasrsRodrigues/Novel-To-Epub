from bs4 import BeautifulSoup, Tag

from app.logging_conf import get_logger
from app.scraper.base import BaseAdapter
from app.models import ChapterContent, ChapterRef, NovelMeta
from app.scraper.errors import ParseError

log = get_logger("novelfull")

class NovelFullAdapter(BaseAdapter):
  name = "novelfull"
  domains = ["novelfull.net"]

  async def fetch_novel(self, url: str) -> NovelMeta:
    
    print("===fetch_novel===")
    soup = BeautifulSoup(await self.client.get_text(url), "lxml")
    
    title_el = soup.select_one("div.title-list h2")
    if(title_el) is None:
      raise ParseError(f"título da novel não encontrado em {url}")
    
    for sp in title_el.select("span"):
      sp.extract()

    title = title_el.get_text(" ", strip=True)

    meta = NovelMeta(
      title=title,
      source_url=url,
      # slug=_slug_from_url(url)
      # author=_extract_authors(soup),
      # cover_url=_extract_cover(sourp,url),
      # description=_extract_description(soup),
      # chapters=_extract_chapters_refs(soup,url)
    )

    log.info(
            "novel_parsed",
            title=meta.title, author=meta.author,
            chapters=len(meta.chapters), slug=meta.slug,
        )
    return meta


  async def fetch_chapter(self, ref: ChapterRef) -> ChapterContent:
    print("fetch_chapter")

# --------------------------- helpers de parse ------------------------------
