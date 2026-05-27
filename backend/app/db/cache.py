"""Repositorio de cache: nunca rebaixar um capitulo ja salvo.

Converte entre as dataclasses de dominio (``app.models``) e as linhas ORM
(``app.db.models``). As operacoes sao sincronas (SQLite local e rapido); o
orquestrador pode envolver em ``asyncio.to_thread`` se quiser.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.db import models as orm
from app.db.database import get_session, init_db
from app.models import ChapterContent, NovelMeta


class ChapterCache:
    def __init__(self) -> None:
        init_db()

    def upsert_novel(self, source: str, slug: str, meta: NovelMeta) -> int:
        """Cria/atualiza os metadados da novel e devolve o id interno."""
        with get_session() as s:
            novel = s.scalar(
                select(orm.Novel).where(orm.Novel.source == source, orm.Novel.slug == slug)
            )
            if novel is None:
                novel = orm.Novel(source=source, slug=slug)
                s.add(novel)
            novel.title = meta.title
            novel.author = meta.author
            novel.cover_url = meta.cover_url
            novel.description = meta.description
            novel.source_url = meta.source_url
            s.commit()
            return novel.id

    def get_chapter(self, novel_id: int, index: int) -> ChapterContent | None:
        with get_session() as s:
            row = s.scalar(
                select(orm.Chapter).where(
                    orm.Chapter.novel_id == novel_id, orm.Chapter.index == index
                )
            )
            if row is None:
                return None
            return ChapterContent(index=row.index, title=row.title, html=row.html, url=row.url)

    def save_chapter(self, novel_id: int, chapter: ChapterContent) -> None:
        """Insere ou atualiza (upsert por (novel_id, index)) — nunca duplica."""
        with get_session() as s:
            row = s.scalar(
                select(orm.Chapter).where(
                    orm.Chapter.novel_id == novel_id,
                    orm.Chapter.index == chapter.index,
                )
            )
            if row is None:
                row = orm.Chapter(novel_id=novel_id, index=chapter.index)
                s.add(row)
            row.title = chapter.title
            row.url = chapter.url
            row.html = chapter.html
            s.commit()

    def has_chapter(self, novel_id: int, index: int) -> bool:
        with get_session() as s:
            return (
                s.scalar(
                    select(orm.Chapter.id).where(
                        orm.Chapter.novel_id == novel_id, orm.Chapter.index == index
                    )
                )
                is not None
            )

    def cached_indices(self, novel_id: int) -> set[int]:
        """Indices ja em cache — usado p/ pular downloads desnecessarios."""
        with get_session() as s:
            return set(
                s.scalars(
                    select(orm.Chapter.index).where(orm.Chapter.novel_id == novel_id)
                ).all()
            )

    def get_novel(self, novel_id: int) -> dict | None:
        """Devolve o detalhe completo (descricao, wiki, ...) ou None."""
        with get_session() as s:
            novel = s.get(orm.Novel, novel_id)
            if novel is None:
                return None
            count = s.scalar(
                select(func.count(orm.Chapter.id)).where(
                    orm.Chapter.novel_id == novel_id
                )
            )
            return {
                "id": novel.id,
                "source": novel.source,
                "slug": novel.slug,
                "title": novel.title,
                "author": novel.author,
                "cover_url": novel.cover_url,
                "description": novel.description,
                "source_url": novel.source_url,
                "wiki_url": novel.wiki_url,
                "wiki_status": novel.wiki_status,
                "chapters": count or 0,
            }

    def list_novels(self) -> list[dict]:
        """Novels em cache com a contagem de capitulos (para a biblioteca)."""
        with get_session() as s:
            rows = s.execute(
                select(orm.Novel, func.count(orm.Chapter.id))
                .outerjoin(orm.Chapter, orm.Chapter.novel_id == orm.Novel.id)
                .group_by(orm.Novel.id)
                .order_by(orm.Novel.title)
            ).all()
            return [
                {
                    "id": n.id,
                    "source": n.source,
                    "slug": n.slug,
                    "title": n.title,
                    "author": n.author,
                    "cover_url": n.cover_url,
                    "chapters": count,
                }
                for (n, count) in rows
            ]
