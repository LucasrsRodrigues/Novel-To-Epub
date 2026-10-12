"""Biblioteca: novels, volumes listados, mirrors e glossario."""

from __future__ import annotations


from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    AddMirrorRequest,
    GlossaryEntryOut,
    MirrorOut,
    NovelDetail,
    NovelSummary,
    VolumeOut,
)
from app.db.cache import ChapterCache
from app.db.mirror_store import MirrorStore
from app.db.volume_store import VolumeStore
from app.scraper.registry import registry
from app.translation.glossary import GlossaryStore

router = APIRouter()


@router.get("/library", response_model=list[NovelSummary])
def library() -> list[dict]:
    return ChapterCache().list_novels()


@router.get("/library/{novel_id}", response_model=NovelDetail)
def get_novel_detail(novel_id: int) -> dict:
    novel = ChapterCache().get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="novel nao encontrada")
    return novel


@router.get("/library/{novel_id}/volumes", response_model=list[VolumeOut])
def list_volumes(novel_id: int) -> list[dict]:
    """Volumes EPUB gerados desta novel (persistido — sobrevive ao restart)."""
    return VolumeStore().list_for_novel(novel_id)


@router.get("/library/{novel_id}/mirrors", response_model=list[MirrorOut])
def list_mirrors(novel_id: int) -> list[dict]:
    """Fontes alternativas (mirrors) desta novel, em ordem de prioridade."""
    return MirrorStore().list_for_novel(novel_id)


@router.post("/library/{novel_id}/mirrors", response_model=MirrorOut, status_code=201)
async def add_mirror(novel_id: int, req: AddMirrorRequest) -> dict:
    """Liga um site alternativo a esta novel (mesmo novel_id => cache preservado).

    Valida que a URL e de um site suportado e que abre como pagina de novel
    (fetch_novel parseia) antes de salvar. O usuario afirma que e a MESMA obra;
    o casamento de capitulos no fallback e por numero de titulo, entao mirrors
    com numeracao levemente diferente (off-by-N) ainda funcionam.
    """
    from app.scraper.http import HttpClient

    novel = ChapterCache().get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="novel nao encontrada")

    url = req.url.strip()
    if not registry.supports(url):
        raise HTTPException(status_code=400, detail=f"site nao suportado: {url}")
    if url == novel["source_url"]:
        raise HTTPException(
            status_code=400, detail="essa ja e a fonte primaria desta novel"
        )

    async with HttpClient() as client:
        adapter = registry.resolve(url, client)
        try:
            await adapter.fetch_novel(url)  # sanity: abre e parseia como novel
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"falha ao validar o mirror: {exc}"
            ) from exc

    return MirrorStore().add(novel_id, adapter.name, url)


@router.delete("/mirrors/{mirror_id}", status_code=204)
def delete_mirror(mirror_id: int) -> None:
    if not MirrorStore().delete(mirror_id):
        raise HTTPException(status_code=404, detail="mirror nao encontrado")


@router.get("/library/{novel_id}/glossary", response_model=list[GlossaryEntryOut])
def get_glossary(novel_id: int) -> list[GlossaryEntryOut]:
    entries = GlossaryStore().list_for_novel(novel_id)
    return [
        GlossaryEntryOut(
            term=e.term,
            canonical_pt=e.canonical_pt,
            kind=e.kind,
            gender=e.gender,
            notes=e.notes,
            confidence=e.confidence,
            first_seen_chapter=e.first_seen_chapter,
            source=e.source,
        )
        for e in entries
    ]


@router.post("/library/{novel_id}/glossary/clean")
def clean_glossary(novel_id: int, apply: bool = False) -> dict:
    """Limpeza do glossario (duplicatas, palavras comuns, lixo).

    Sem ``apply`` so devolve o relatorio do que seria feito; com ``apply=true``
    aplica e devolve o mesmo relatorio. Ver app.translation.glossary_cleanup.
    """
    from app.translation.glossary_cleanup import apply_cleanup, plan_cleanup

    if ChapterCache().get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel nao encontrada")
    plan = plan_cleanup(novel_id)
    if apply:
        apply_cleanup(plan)
    return {**plan.summary(), "applied": apply}
