"""Capitulos do volume e traducoes manuais."""

from __future__ import annotations


from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    ChapterDetail,
    ChapterSummary,
    ChapterTranslationUpdate,
)
from app.db.cache import ChapterCache
from app.db.database import get_session
from app.db import models as orm
from sqlalchemy import select
from app.translation.translation_store import TranslationStore

router = APIRouter()


@router.get(
    "/library/{novel_id}/chapters",
    response_model=list[ChapterSummary],
)
def list_chapters(
    novel_id: int,
    language: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> list[ChapterSummary]:
    """Lista capitulos em cache (com info de traducao se `language` passado).
    `start`/`end` permitem filtrar por range (mesma faixa do volume)."""
    with get_session() as s:
        novel = s.get(orm.Novel, novel_id)
        if novel is None:
            raise HTTPException(status_code=404, detail="novel nao encontrada")
        q = select(orm.Chapter).where(orm.Chapter.novel_id == novel_id)
        if start is not None:
            q = q.where(orm.Chapter.index >= start)
        if end is not None:
            q = q.where(orm.Chapter.index <= end)
        q = q.order_by(orm.Chapter.index)
        rows = s.scalars(q).all()
        # Translation lookup em batch
        translations: dict[int, orm.TranslatedChapter] = {}
        if language:
            tr_rows = s.scalars(
                select(orm.TranslatedChapter).where(
                    orm.TranslatedChapter.novel_id == novel_id,
                    orm.TranslatedChapter.language == language,
                )
            ).all()
            translations = {t.chapter_index: t for t in tr_rows}
        out: list[ChapterSummary] = []
        for r in rows:
            t = translations.get(r.index)
            out.append(ChapterSummary(
                index=r.index, title_en=r.title,
                title_pt=t.title if t else None,
                has_translation=t is not None,
                translation_source=t.model if t else None,
            ))
        return out


@router.get(
    "/library/{novel_id}/chapters/{idx}",
    response_model=ChapterDetail,
)
def get_chapter_detail(
    novel_id: int, idx: int, language: str | None = None,
) -> ChapterDetail:
    cache = ChapterCache()
    ch = cache.get_chapter(novel_id, idx)
    if ch is None:
        raise HTTPException(status_code=404, detail="cap nao esta em cache")
    t_html: str | None = None
    t_title: str | None = None
    source: str | None = None
    if language:
        with get_session() as s:
            tr = s.scalar(
                select(orm.TranslatedChapter).where(
                    orm.TranslatedChapter.novel_id == novel_id,
                    orm.TranslatedChapter.chapter_index == idx,
                    orm.TranslatedChapter.language == language,
                )
            )
            if tr is not None:
                t_html, t_title, source = tr.html, tr.title, tr.model
    return ChapterDetail(
        index=ch.index, title_en=ch.title, html_en=ch.html,
        title_pt=t_title, html_pt=t_html,
        translation_source=source, language=language,
    )


@router.put(
    "/library/{novel_id}/chapters/{idx}/translation",
    response_model=ChapterDetail,
)
def upsert_chapter_translation(
    novel_id: int, idx: int, body: ChapterTranslationUpdate,
) -> ChapterDetail:
    """Salva tradução manual. `model='manual'` distingue de geração IA."""
    cache = ChapterCache()
    ch = cache.get_chapter(novel_id, idx)
    if ch is None:
        raise HTTPException(status_code=404, detail="cap nao esta em cache")
    TranslationStore().save(
        novel_id=novel_id, chapter_index=idx, language=body.language,
        title=body.title, html=body.html, model="manual", glossary_size=0,
    )
    return ChapterDetail(
        index=ch.index, title_en=ch.title, html_en=ch.html,
        title_pt=body.title, html_pt=body.html,
        translation_source="manual", language=body.language,
    )


@router.delete(
    "/library/{novel_id}/chapters/{idx}/translation",
    status_code=204,
)
def delete_chapter_translation(
    novel_id: int, idx: int, language: str,
) -> None:
    with get_session() as s:
        tr = s.scalar(
            select(orm.TranslatedChapter).where(
                orm.TranslatedChapter.novel_id == novel_id,
                orm.TranslatedChapter.chapter_index == idx,
                orm.TranslatedChapter.language == language,
            )
        )
        if tr is None:
            raise HTTPException(status_code=404, detail="tradução nao existe")
        s.delete(tr)
        s.commit()
