"""Capas por IA: regerar, galeria, arquivo/wallpapers."""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.jobs import JobManager
from app.api.schemas import (
    CoverOut,
    JobStatus,
    RegenerateCoverRequest,
)
from app.db.cache import ChapterCache
from app.db.cover_cache import CoverCache
from app.db.volume_store import VolumeStore
from app.api.deps import get_jobs

router = APIRouter()


@router.post(
    "/volumes/{volume_id}/regenerate-cover",
    response_model=JobStatus,
    status_code=201,
)
def regenerate_volume_cover(
    volume_id: int,
    body: RegenerateCoverRequest | None = None,
    jobs: JobManager = Depends(get_jobs),
) -> JobStatus:
    """Gera (ou regera) a capa por IA do volume e re-enqueue.

    Funciona mesmo pra volume que foi baixado SEM capa IA: o re-enqueue força
    ``ai_cover=True``, então a capa nasce agora. Cache de capítulos/tradução é
    reusado e o ``output_path`` é o mesmo (mesmo volume_title + idioma) → o
    upsert atualiza o MESMO registro (vira ai_cover=True), sem criar duplicata.
    """
    vol = VolumeStore().get(volume_id)
    if vol is None:
        raise HTTPException(status_code=404, detail="volume nao encontrado")
    # Caminho LEVE "so capa": regera a capa do cache + recompila o .epub, sem
    # re-baixar nem re-traduzir (o fluxo antigo re-enfileirava um download
    # completo, que re-tentava caps que falharam → storm de 429).
    new_job = jobs.enqueue_cover_regen(vol, body.cover_style if body else None)
    return new_job.to_status()


@router.post(
    "/library/{novel_id}/regenerate-all-covers",
    response_model=list[JobStatus],
    status_code=201,
)
def regenerate_all_covers(
    novel_id: int,
    body: RegenerateCoverRequest | None = None,
    jobs: JobManager = Depends(get_jobs),
) -> list[JobStatus]:
    """Regera TODAS as capas IA da novel de uma vez, pra alinhar a coleção.

    Reseta a âncora de série (paleta+luz) e enfileira os volumes em ORDEM (o 1o
    re-estabelece a âncora a partir da nova arte, os demais herdam). Custa
    ~R$0,20 por volume. ``cover_style`` opcional troca o estilo travado de todos.
    """
    vols = VolumeStore().list_for_novel(novel_id)
    # So os volumes que ja tem capa IA (a "coleção"); ordena por capitulo inicial
    # asc pra o Volume 1 rodar primeiro e definir a âncora da serie.
    targets = sorted((v for v in vols if v["ai_cover"]), key=lambda v: v["start"])
    if not targets:
        raise HTTPException(status_code=404, detail="nenhuma capa IA pra regerar nesta novel")

    style = body.cover_style if body else None
    if style:
        # Estilo explicito vira o default de todos (e ja zera a âncora antiga).
        ChapterCache().set_default_cover_style(novel_id, style)
    else:
        # Sem troca de estilo: so reseta a âncora pra re-derivar da nova 1a capa.
        ChapterCache().set_series_anchor(novel_id, None, None)

    out: list[JobStatus] = []
    for v in targets:
        # Caminho leve "so capa" — sem re-download/traducao. O 1o job re-estabelece
        # a âncora (resetada acima); os demais herdam → coleção coerente.
        out.append(jobs.enqueue_cover_regen(v, style).to_status())
    return out


# ---------------------------------------------------------------- galeria de capas
_COVER_KINDS = {"titled", "raw", "phone", "pc", "pc_hd"}
_WALLPAPER_KINDS = {"phone", "pc", "pc_hd"}
_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


@router.get("/library/{novel_id}/covers", response_model=list[CoverOut])
def list_covers(novel_id: int) -> list[dict]:
    """Capas geradas por IA desta novel — alimenta a galeria (sem os BLOBs)."""
    return CoverCache().list_for_novel(novel_id)


# `def` (nao async): o FastAPI roda no threadpool — o derive_wallpaper (Pillow)
# e a leitura do BLOB nao travam o event loop.
@router.get("/covers/{cover_id}/file")
def cover_file(
    cover_id: int,
    kind: str = "titled",
    native: bool = False,
    download: bool = False,
) -> Response:
    """Serve a imagem de uma capa.

    ``kind``: titled (com titulo) | raw (sem texto) | phone (9:16) | pc (16:9).
    Wallpapers (phone/pc) sao derivados LOCALMENTE da arte crua por padrao; com
    ``native=true`` serve a variante nativa (Gemini) — 404 se ainda nao gerada.
    ``download=true`` forca attachment (baixar em vez de exibir inline).
    """
    if kind not in _COVER_KINDS:
        raise HTTPException(status_code=400, detail=f"kind invalido: {kind}")
    row = CoverCache().get_by_id(cover_id)
    if row is None:
        raise HTTPException(status_code=404, detail="capa nao encontrada")

    if kind == "titled":
        data, mime = row["image_data"], row["mime_type"]
    elif kind == "raw":
        if row["image_data_raw"] is None:
            raise HTTPException(
                status_code=409,
                detail="arte sem texto indisponivel — regenere a capa pra liberar",
            )
        data, mime = row["image_data_raw"], row["mime_type"]
    else:  # phone | pc
        from app.image_gen.wallpaper import ASPECT_BY_FORMAT, derive_wallpaper

        if native:
            variant = CoverCache().get_variant(cover_id, ASPECT_BY_FORMAT[kind])
            if variant is None:
                raise HTTPException(
                    status_code=404,
                    detail="wallpaper nativo ainda nao gerado pra este formato",
                )
            data, mime = variant
        else:
            if row["image_data_raw"] is None:
                raise HTTPException(
                    status_code=409,
                    detail="arte sem texto indisponivel — regenere a capa pra liberar",
                )
            data, mime = derive_wallpaper(row["image_data_raw"], kind)

    headers = {}
    if download:
        from slugify import slugify

        base = slugify(row["volume_title"] or f"capa-{cover_id}")
        suffix = {"titled": "", "raw": "-sem-texto", "phone": "-wallpaper-celular",
                  "pc": "-wallpaper-pc", "pc_hd": "-wallpaper-pc-2560"}[kind]
        ext = _EXT_BY_MIME.get(mime, "png")
        headers["Content-Disposition"] = f'attachment; filename="{base}{suffix}.{ext}"'
    return Response(content=data, media_type=mime, headers=headers)


@router.post("/covers/{cover_id}/native", response_model=CoverOut, status_code=201)
async def generate_native_wallpaper_route(cover_id: int, fmt: str) -> dict:
    """Gera (Gemini, ~R$0,20) o wallpaper NATIVO na proporcao do formato e cacheia.
    ``fmt``: phone (9:16) | pc | pc_hd (ambos 16:9 — compartilham a variante)."""
    from app.image_gen.cover_generator import generate_native_wallpaper, CoverGenError

    if fmt not in _WALLPAPER_KINDS:
        raise HTTPException(status_code=400, detail=f"fmt invalido: {fmt}")
    row = CoverCache().get_by_id(cover_id)
    if row is None:
        raise HTTPException(status_code=404, detail="capa nao encontrada")
    try:
        await generate_native_wallpaper(cover_id=cover_id, fmt=fmt)
    except CoverGenError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Devolve o registro atualizado (native_aspects agora inclui o novo formato).
    covers = CoverCache().list_for_novel(row["novel_id"])
    updated = next((c for c in covers if c["id"] == cover_id), None)
    if updated is None:
        raise HTTPException(status_code=404, detail="capa sumiu apos gerar variante")
    return updated


@router.post("/covers/{cover_id}/regenerate-art", response_model=CoverOut, status_code=201)
async def regenerate_cover_art_route(cover_id: int) -> dict:
    """Re-gera a arte (Gemini, ~R$0,20) reusando o prompt salvo — libera a versao
    'sem texto' (+ wallpapers) em capas antigas que so tinham a versao com titulo."""
    from app.image_gen.cover_generator import regenerate_cover_art, CoverGenError

    row = CoverCache().get_by_id(cover_id)
    if row is None:
        raise HTTPException(status_code=404, detail="capa nao encontrada")
    try:
        await regenerate_cover_art(cover_id=cover_id)
    except CoverGenError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    covers = CoverCache().list_for_novel(row["novel_id"])
    updated = next((c for c in covers if c["id"] == cover_id), None)
    if updated is None:
        raise HTTPException(status_code=404, detail="capa sumiu apos regerar arte")
    return updated
