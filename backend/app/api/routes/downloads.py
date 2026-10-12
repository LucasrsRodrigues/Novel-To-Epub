"""Captura (preview + jobs de download) e acoes sobre um job."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.jobs import JobManager
from app.api.schemas import (
    DownloadRequest,
    JobStatus,
    NovelPreviewOut,
    NovelPreviewRequest,
    RegenerateCoverRequest,
    VolumePreview,
)
from app.db.cache import ChapterCache
from app.db.database import get_session
from app.db import models as orm
from sqlalchemy import select
from app.db.volume_store import VolumeStore
from app.scraper.registry import registry
from app.api.deps import get_jobs, kindle_config, send_file_to_kindle

router = APIRouter()


@router.post("/preview-novel", response_model=NovelPreviewOut)
async def preview_novel(req: NovelPreviewRequest) -> NovelPreviewOut:
    """Carrega metadados + lista de capítulos da novel SEM persistir nada e SEM
    custo de IA. UI usa pra mostrar capa/título/dropdown de volume antes da captura.

    Volumes são detectados a partir de `ChapterRef.volume_label` preenchido
    pelo adapter (NovelMania sim; NovelBin não → retorna `volumes: []`).
    """
    from app.scraper.http import HttpClient
    url = req.url.strip()
    if not registry.supports(url):
        raise HTTPException(status_code=400, detail=f"site nao suportado: {url}")
    async with HttpClient() as client:
        adapter = registry.resolve(url, client)
        try:
            meta = await adapter.fetch_novel(url)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"falha ao parsear novel: {exc}"
            ) from exc

    # Agrega chapters por volume_label preservando ordem
    volumes: list[VolumePreview] = []
    current: VolumePreview | None = None
    for ch in meta.chapters:
        label = ch.volume_label
        if label is None:
            continue
        if current is None or current.name != label:
            if current is not None:
                volumes.append(current)
            current = VolumePreview(
                name=label, start=ch.index, end=ch.index, chapter_count=1,
            )
        else:
            current.end = ch.index
            current.chapter_count += 1
    if current is not None:
        volumes.append(current)

    # Se a novel ja foi capturada, devolve o estilo de capa default salvo pra UI
    # pre-selecionar o seletor. Busca por source_url (chave estavel da novel).
    default_cover_style = ChapterCache().get_default_cover_style(meta.source_url)

    return NovelPreviewOut(
        title=meta.title,
        author=meta.author,
        cover_url=meta.cover_url,
        description=meta.description,
        total_chapters=len(meta.chapters),
        volumes=volumes,
        default_cover_style=default_cover_style,
    )


@router.post("/downloads", response_model=JobStatus, status_code=201)
def create_download(
    req: DownloadRequest, jobs: JobManager = Depends(get_jobs)
) -> JobStatus:
    if not registry.supports(req.url):
        raise HTTPException(status_code=400, detail=f"site nao suportado: {req.url}")
    return jobs.enqueue(req).to_status()


@router.get("/downloads", response_model=list[JobStatus])
def list_downloads(jobs: JobManager = Depends(get_jobs)) -> list[JobStatus]:
    return [j.to_status() for j in jobs.list()]


@router.get("/downloads/{job_id}", response_model=JobStatus)
def get_download(job_id: str, jobs: JobManager = Depends(get_jobs)) -> JobStatus:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job nao encontrado")
    return job.to_status()


@router.post("/downloads/{job_id}/cancel", response_model=JobStatus)
def cancel_download(job_id: str, jobs: JobManager = Depends(get_jobs)) -> JobStatus:
    """Cancela um job 'queued' ou 'running'. Idempotente em estados terminais."""
    job = jobs.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job nao encontrado")
    return job.to_status()


@router.post("/downloads/{job_id}/resume", response_model=JobStatus, status_code=201)
def resume_download(job_id: str, jobs: JobManager = Depends(get_jobs)) -> JobStatus:
    """Continua uma captura cancelada/com erro reaproveitando os mesmos params.

    O cache faz retomar de onde parou (so baixa/traduz o que faltou). 409 se o
    job nao esta num estado retomavel (ex: ainda rodando ou ja concluido).
    """
    job = jobs.resume(job_id)
    if job is None:
        existing = jobs.get(job_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="job nao encontrado")
        raise HTTPException(
            status_code=409,
            detail=f"job em estado '{existing.status}' nao pode ser retomado",
        )
    return job.to_status()


@router.delete("/downloads/{job_id}", status_code=204)
def discard_download(job_id: str, jobs: JobManager = Depends(get_jobs)) -> None:
    """Descarta uma captura pendente (cancelada/erro/interrompida) + sua intencao
    persistida. Nao apaga capitulos/traducao do cache. 409 se ainda esta ativo."""
    if not jobs.discard(job_id):
        raise HTTPException(
            status_code=409, detail="job ativo — cancele antes de descartar"
        )


@router.get("/downloads/{job_id}/file")
def download_file(job_id: str, jobs: JobManager = Depends(get_jobs)) -> FileResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job nao encontrado")
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=409, detail="epub ainda nao esta pronto")
    path = Path(job.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="arquivo nao encontrado")
    return FileResponse(
        path, media_type="application/epub+zip", filename=path.name
    )


@router.post("/downloads/{job_id}/regenerate-cover", response_model=JobStatus, status_code=201)
def regenerate_cover(
    job_id: str,
    body: RegenerateCoverRequest | None = None,
    jobs: JobManager = Depends(get_jobs),
) -> JobStatus:
    """Regera a capa por IA do volume que este job gerou.

    Delega pro caminho leve "so capa" (o mesmo de /volumes/{id}/regenerate-cover):
    regera do cache e recompila o .epub, sem re-baixar. Antes esta rota
    re-enfileirava o download inteiro — perdia o skip_chapters do volume (os
    caps-lixo ignorados voltavam) e APAGAVA a capa antes de gerar a nova (se a
    geracao falhasse, o volume ficava sem capa).
    """
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job nao encontrado")

    vol = VolumeStore().get(job.volume_id) if job.volume_id else None
    if vol is None:
        # Jobs de versoes antigas nao tinham volume_id: casa pelo volume da novel
        # com o mesmo titulo e idioma (o mesmo par que define o arquivo).
        with get_session() as s:
            novel = s.scalar(select(orm.Novel).where(orm.Novel.source_url == job.url))
        candidates = VolumeStore().list_for_novel(novel.id) if novel else []
        vol = next(
            (
                v for v in candidates
                if v["volume_title"] == job.volume_title and v["translate_to"] == job.translate_to
            ),
            None,
        )
    if vol is None:
        raise HTTPException(
            status_code=409,
            detail="este job nao gerou um volume — conclua a captura antes de regerar a capa",
        )
    return jobs.enqueue_cover_regen(vol, body.cover_style if body else None).to_status()


@router.post("/downloads/{job_id}/kindle")
async def send_to_kindle(
    job_id: str, jobs: JobManager = Depends(get_jobs)
) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job nao encontrado")
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=409, detail="epub ainda nao esta pronto")

    cfg = kindle_config()
    try:
        await send_file_to_kindle(cfg, job.output_path)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"falha no envio: {exc}") from exc

    return {"status": "sent", "to": cfg["kindle_email"]}
