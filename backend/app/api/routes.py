"""Rotas REST da API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

from app import __version__
from app.api.jobs import JobManager
from app.api.schemas import (
    ChapterDetail,
    ChapterSummary,
    ChapterTranslationUpdate,
    CoverOut,
    DownloadRequest,
    GlossaryEntryOut,
    JobStatus,
    NovelDetail,
    NovelPreviewOut,
    NovelPreviewRequest,
    NovelSummary,
    RegenerateCoverRequest,
    VolumePreview,
    SettingsOut,
    SettingsUpdate,
    SiteInfo,
    RecentUsageInfo,
    TranslationDebugStatus,
    UsageByNovel,
    UsageByProvider,
    UsageDay,
    UsageSummary,
    VolumeOut,
    VolumePinInfo,
)
from app.translation.pin_store import VolumePinStore
from app.db.cache import ChapterCache
from app.db.cover_cache import CoverCache
from app.db.database import get_session
from app.db import models as orm
from sqlalchemy import select
from app.db.settings_store import SettingsStore
from app.db.usage_store import UsageStore
from app.db.volume_store import VolumeStore
from app.translation.translation_store import TranslationStore
from app.kindle.sender import send_epub_to_kindle
from app.scraper.registry import registry
from app.translation.glossary import GlossaryStore

router = APIRouter(prefix="/api")


def get_jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def _settings_out(cfg: dict) -> SettingsOut:
    raw_order = cfg.get("cascade_order") or "groq,openrouter,cerebras,gemini"
    order = (
        [p.strip() for p in raw_order.split(",") if p.strip()]
        if isinstance(raw_order, str)
        else list(raw_order)
    )
    raw_styles = cfg.get("cover_styles_enabled") or ""
    cover_styles = (
        [s.strip() for s in raw_styles.split(",") if s.strip()]
        if isinstance(raw_styles, str)
        else list(raw_styles)
    )
    return SettingsOut(
        smtp_host=cfg["smtp_host"],
        smtp_port=cfg["smtp_port"],
        smtp_user=cfg["smtp_user"],
        smtp_password_set=bool(cfg["smtp_password"]),
        smtp_use_tls=cfg["smtp_use_tls"],
        smtp_from=cfg["smtp_from"],
        kindle_email=cfg["kindle_email"],
        gemini_api_key_set=bool(cfg.get("gemini_api_key")),
        target_language=cfg.get("target_language") or "pt-BR",
        translation_model=cfg.get("translation_model") or "gemini-2.5-flash",
        groq_api_key_set=bool(cfg.get("groq_api_key")),
        openrouter_api_key_set=bool(cfg.get("openrouter_api_key")),
        cerebras_api_key_set=bool(cfg.get("cerebras_api_key")),
        groq_model=cfg.get("groq_model") or None,
        openrouter_model=cfg.get("openrouter_model") or None,
        cerebras_model=cfg.get("cerebras_model") or None,
        default_models=_provider_defaults(),
        cascade_order=order,
        cover_styles_enabled=cover_styles,
    )


def _provider_defaults() -> dict[str, str]:
    """Espelha factory.DEFAULT_MODELS pra UI mostrar como placeholder."""
    from app.translation.factory import DEFAULT_MODELS
    return dict(DEFAULT_MODELS)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/sites", response_model=list[SiteInfo])
def sites() -> list[SiteInfo]:
    return [SiteInfo(name=c.name, domains=c.domains) for c in registry.adapters]


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


@router.delete("/volumes/{volume_id}", status_code=204)
def delete_volume(volume_id: int) -> None:
    """Remove um volume gerado: apaga o registro e o .epub do disco.

    Não toca no cache de capítulos/tradução/glossário/capa — só o volume.
    Usado pra limpar duplicatas (ex: a versão original sobrando ao lado da
    traduzida, ou um volume com tradução incompleta que o usuário descartou).
    """
    if not VolumeStore().delete(volume_id, delete_file=True):
        raise HTTPException(status_code=404, detail="volume nao encontrado")


@router.get("/volumes/{volume_id}/file")
def download_volume_file(volume_id: int) -> FileResponse:
    vol = VolumeStore().get(volume_id)
    if vol is None:
        raise HTTPException(status_code=404, detail="volume nao encontrado")
    path = Path(vol["output_path"])
    if not path.exists():
        raise HTTPException(
            status_code=410,
            detail=f"arquivo .epub nao existe mais em disco ({path.name}) — re-gere o volume",
        )
    return FileResponse(
        path, media_type="application/epub+zip", filename=path.name
    )


@router.post("/volumes/{volume_id}/kindle")
async def send_volume_to_kindle(volume_id: int) -> dict:
    vol = VolumeStore().get(volume_id)
    if vol is None:
        raise HTTPException(status_code=404, detail="volume nao encontrado")
    path = Path(vol["output_path"])
    if not path.exists():
        raise HTTPException(
            status_code=410, detail="arquivo .epub nao existe mais em disco"
        )

    cfg = SettingsStore().get()
    missing = [
        k for k in ("smtp_host", "smtp_from", "kindle_email") if not cfg.get(k)
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"configuracao incompleta (faltam: {', '.join(missing)})",
        )
    try:
        await send_epub_to_kindle(
            str(path),
            host=cfg["smtp_host"], port=cfg["smtp_port"],
            username=cfg["smtp_user"], password=cfg["smtp_password"],
            sender=cfg["smtp_from"], to=cfg["kindle_email"],
            use_tls=cfg["smtp_use_tls"],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"falha no envio: {exc}") from exc
    return {"status": "sent", "to": cfg["kindle_email"]}


@router.post("/volumes/{volume_id}/rebuild", response_model=VolumeOut)
async def rebuild_volume(volume_id: int) -> dict:
    """Re-monta o EPUB do cache atual (zero token Gemini, zero re-download).
    Util pra: mudancas no builder/CSS, traducao manual adicionada, .epub sumiu."""
    from app.rebuild import rebuild_volume_epub, RebuildError
    try:
        await rebuild_volume_epub(volume_id)
    except RebuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    vol = VolumeStore().get(volume_id)
    if vol is None:
        raise HTTPException(status_code=404, detail="volume sumiu apos rebuild")
    return vol


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
    # Se ja tinha capa IA cacheada, apaga pra forçar MISS → regenera. Se nao
    # tinha (primeira capa), o delete e no-op.
    CoverCache().delete(vol["novel_id"], vol["volume_title"])
    new_job = jobs.enqueue(
        DownloadRequest(
            url=vol["source_url"],
            start=vol["start"],
            end=vol["end"],
            with_cover=vol["with_cover"],
            translate_to=vol["translate_to"],
            volume_title=vol["volume_title"],
            ai_cover=True,
            cover_style=body.cover_style if body else None,
        )
    )
    return new_job.to_status()


# ---------------------------------------------------------------- galeria de capas
_COVER_KINDS = {"titled", "raw", "phone", "pc"}
_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


@router.get("/library/{novel_id}/covers", response_model=list[CoverOut])
def list_covers(novel_id: int) -> list[dict]:
    """Capas geradas por IA desta novel — alimenta a galeria (sem os BLOBs)."""
    return CoverCache().list_for_novel(novel_id)


@router.get("/covers/{cover_id}/file")
async def cover_file(
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
                  "pc": "-wallpaper-pc"}[kind]
        ext = _EXT_BY_MIME.get(mime, "png")
        headers["Content-Disposition"] = f'attachment; filename="{base}{suffix}.{ext}"'
    return Response(content=data, media_type=mime, headers=headers)


@router.post("/covers/{cover_id}/native", response_model=CoverOut, status_code=201)
async def generate_native_wallpaper_route(cover_id: int, fmt: str) -> dict:
    """Gera (Gemini, ~R$0,20) o wallpaper NATIVO na proporcao do formato e cacheia.
    ``fmt``: phone (9:16) | pc (16:9)."""
    from app.image_gen.cover_generator import generate_native_wallpaper, CoverGenError

    if fmt not in {"phone", "pc"}:
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


@router.get("/usage/summary", response_model=UsageSummary)
def usage_summary() -> dict:
    return UsageStore().summary()


@router.get("/usage/by-day", response_model=list[UsageDay])
def usage_by_day(days: int = 30) -> list[dict]:
    return UsageStore().by_day(days=max(1, min(days, 365)))


@router.get("/usage/by-novel", response_model=list[UsageByNovel])
def usage_by_novel() -> list[dict]:
    return UsageStore().by_novel()


@router.get("/usage/by-provider", response_model=list[UsageByProvider])
def usage_by_provider() -> list[dict]:
    return UsageStore().by_provider()


@router.get("/debug/translation-status", response_model=TranslationDebugStatus)
def translation_debug_status() -> TranslationDebugStatus:
    """Snapshot do estado: quais providers estão configurados, qual ordem,
    quais pins existem (volume → provider gravado), e últimas 20 chamadas
    de tradução. Usado pra diagnosticar 'meu cascade só usa Gemini'."""
    from app.translation.factory import _read_keys, DEFAULT_MODELS

    cfg = SettingsStore().get()
    keys = _read_keys(cfg)
    active = [name for name, key in keys.items() if key]
    inactive = [name for name, key in keys.items() if not key]

    raw_order = cfg.get("cascade_order") or "groq,openrouter,cerebras,gemini"
    order = (
        [p.strip() for p in raw_order.split(",") if p.strip()]
        if isinstance(raw_order, str)
        else list(raw_order)
    )

    # Pins
    with get_session() as s:
        pin_rows = s.execute(
            select(orm.VolumeTranslatorPin, orm.Novel.title)
            .outerjoin(orm.Novel, orm.Novel.id == orm.VolumeTranslatorPin.novel_id)
            .order_by(orm.VolumeTranslatorPin.created_at.desc())
        ).all()
    pins = [
        VolumePinInfo(
            novel_id=p.novel_id, novel_title=t or "(desconhecida)",
            volume_title=p.volume_title or None, language=p.language,
            provider=p.provider, model=p.model, created_at=p.created_at,
        )
        for (p, t) in pin_rows
    ]

    # Últimas 20 chamadas
    with get_session() as s:
        recent_rows = s.scalars(
            select(orm.GeminiUsage)
            .order_by(orm.GeminiUsage.created_at.desc())
            .limit(20)
        ).all()
    recent = [
        RecentUsageInfo(
            op=r.op, provider=r.provider, model=r.model,
            novel_id=r.novel_id, chapter_index=r.chapter_index,
            cost_usd=r.cost_usd, error_message=r.error_message,
            created_at=r.created_at,
        )
        for r in recent_rows
    ]

    return TranslationDebugStatus(
        active_providers=active, inactive_providers=inactive,
        cascade_order=order, pins=pins, recent_usage=recent,
    )


@router.delete("/volumes/{volume_id}/translator-pin", status_code=204)
def reset_volume_pin(volume_id: int) -> None:
    """Apaga o pin do volume. Próximo cap traduzido roda o cascade do zero
    (tenta o 1º provider configurado). Util quando pin gravou no provider errado."""
    vol = VolumeStore().get(volume_id)
    if vol is None:
        raise HTTPException(status_code=404, detail="volume nao encontrado")
    lang = vol["translate_to"] or "pt-BR"
    cleared = VolumePinStore().clear(vol["novel_id"], vol["volume_title"], lang)
    if not cleared:
        raise HTTPException(status_code=404, detail="volume nao tinha pin")


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


@router.get("/settings", response_model=SettingsOut)
def get_settings() -> SettingsOut:
    return _settings_out(SettingsStore().get())


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate) -> SettingsOut:
    payload = body.model_dump(exclude_unset=True)
    # cascade_order chega como lista no JSON, serializa pra CSV no DB
    if "cascade_order" in payload and isinstance(payload["cascade_order"], list):
        payload["cascade_order"] = ",".join(payload["cascade_order"])
    # cover_styles_enabled idem: lista de ids → CSV
    if "cover_styles_enabled" in payload and isinstance(payload["cover_styles_enabled"], list):
        payload["cover_styles_enabled"] = ",".join(payload["cover_styles_enabled"])
    cfg = SettingsStore().update(payload)
    return _settings_out(cfg)


@router.post("/downloads/{job_id}/regenerate-cover", response_model=JobStatus, status_code=201)
def regenerate_cover(
    job_id: str,
    body: RegenerateCoverRequest | None = None,
    jobs: JobManager = Depends(get_jobs),
) -> JobStatus:
    """Gera (ou regera) a capa por IA e re-enqueue o mesmo job.

    Funciona mesmo pra job baixado SEM capa IA: o re-enqueue força ai_cover=True.
    Cache de capítulo + tradução é reusado; só a capa nasce/regenera."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job nao encontrado")

    # Resolve novel_id pela URL do job (que e a source_url da novel cadastrada).
    with get_session() as s:
        novel = s.scalar(select(orm.Novel).where(orm.Novel.source_url == job.url))
    if novel is None:
        raise HTTPException(
            status_code=404,
            detail="novel correspondente nao esta no cache (re-rode o download primeiro)",
        )

    CoverCache().delete(novel.id, job.volume_title)

    # Re-enqueue com mesmos params (igual ao "Continuar tradução")
    new_job = jobs.enqueue(
        DownloadRequest(
            url=job.url,
            start=job.start,
            end=job.end,
            with_cover=job.with_cover,
            translate_to=job.translate_to,
            volume_title=job.volume_title,
            ai_cover=True,
            cover_style=body.cover_style if body else None,
        )
    )
    return new_job.to_status()


@router.post("/downloads/{job_id}/kindle")
async def send_to_kindle(
    job_id: str, jobs: JobManager = Depends(get_jobs)
) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job nao encontrado")
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=409, detail="epub ainda nao esta pronto")

    cfg = SettingsStore().get()
    missing = [
        k for k in ("smtp_host", "smtp_from", "kindle_email") if not cfg.get(k)
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"configuracao incompleta (faltam: {', '.join(missing)}) — use PUT /api/settings",
        )

    try:
        await send_epub_to_kindle(
            job.output_path,
            host=cfg["smtp_host"],
            port=cfg["smtp_port"],
            username=cfg["smtp_user"],
            password=cfg["smtp_password"],
            sender=cfg["smtp_from"],
            to=cfg["kindle_email"],
            use_tls=cfg["smtp_use_tls"],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"falha no envio: {exc}") from exc

    return {"status": "sent", "to": cfg["kindle_email"]}
