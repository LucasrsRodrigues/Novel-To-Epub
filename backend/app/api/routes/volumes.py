"""Volumes gerados: arquivo, .zip, Kindle, recompilar, renomear, pin."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from app.api.schemas import (
    RenameVolumeRequest,
    VolumeOut,
)
from app.translation.pin_store import VolumePinStore
from app.db.cache import ChapterCache
from app.db.volume_store import VolumeStore
from app.api.deps import kindle_config, send_file_to_kindle

router = APIRouter()


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


def _ready_volumes(novel_id: int) -> list[dict]:
    """Volumes 'prontos' de uma novel: pula os de tradução incompleta (mesma
    regra da UI, que esconde .epub/Kindle quando faltam caps traduzidos)."""
    vols = VolumeStore().list_for_novel(novel_id)
    return [
        v for v in vols
        if not (v["translate_to"] and (v["translation_failed"] or 0) > 0)
    ]


@router.get("/library/{novel_id}/volumes.zip")
def download_all_volumes(novel_id: int) -> Response:
    """Baixa TODOS os volumes prontos da novel num único .zip (sem recompactar —
    os .epub já são comprimidos). Pula volumes com tradução incompleta ou cujo
    arquivo sumiu do disco."""
    import io
    import zipfile
    from slugify import slugify

    novel = ChapterCache().get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="novel nao encontrada")

    buf = io.BytesIO()
    added = 0
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for v in _ready_volumes(novel_id):
            path = Path(v["output_path"])
            if not path.exists():
                continue
            # Garante nome único dentro do zip (evita colisão de basename).
            name = path.name
            if name in used_names:
                name = f"{path.stem}-{v['id']}{path.suffix}"
            used_names.add(name)
            zf.write(path, arcname=name)
            added += 1

    if added == 0:
        raise HTTPException(status_code=404, detail="nenhum volume pronto pra baixar")

    zip_name = f"{slugify(novel.get('title') or f'novel-{novel_id}')}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.post("/library/{novel_id}/kindle-all")
async def send_all_to_kindle(novel_id: int) -> dict:
    """Envia TODOS os volumes prontos da novel pro Kindle, em sequência. Devolve
    o resultado por volume (não falha o lote inteiro se um volume der erro)."""
    novel = ChapterCache().get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="novel nao encontrada")

    cfg = kindle_config()

    ready = _ready_volumes(novel_id)
    if not ready:
        raise HTTPException(status_code=404, detail="nenhum volume pronto pra enviar")

    results: list[dict] = []
    sent = 0
    for v in ready:
        title = v["volume_title"] or f"caps {v['start']}-{v['end']}"
        path = Path(v["output_path"])
        if not path.exists():
            results.append({"volume_id": v["id"], "title": title, "ok": False,
                            "error": "arquivo .epub sumiu do disco"})
            continue
        try:
            await send_file_to_kindle(cfg, str(path))
            sent += 1
            results.append({"volume_id": v["id"], "title": title, "ok": True})
        except Exception as exc:
            results.append({"volume_id": v["id"], "title": title, "ok": False,
                            "error": str(exc)})

    return {"to": cfg["kindle_email"], "sent": sent,
            "total": len(ready), "results": results}


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

    cfg = kindle_config()
    try:
        await send_file_to_kindle(cfg, str(path))
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


@router.post("/volumes/{volume_id}/rename", response_model=VolumeOut)
async def rename_volume(volume_id: int, body: RenameVolumeRequest) -> dict:
    """Renomeia o volume: re-compoe o texto da capa sobre a arte EXISTENTE (sem
    IA, custo zero) e remonta o .epub com o novo titulo.

    Nao re-baixa, nao re-traduz e nao gera arte nova — so o overlay de texto da
    capa e refeito a partir da arte crua salva, e o .epub e remontado do cache
    (mesmo arquivo no disco). 409 se a capa por IA nao guardou a arte sem texto
    (capas antigas): nesse caso, regenere a arte da capa antes.
    """
    from app.rebuild import rebuild_volume_epub, RebuildError
    from app.image_gen.cover_generator import recompose_cover_text

    vs = VolumeStore()
    vol = vs.get(volume_id)
    if vol is None:
        raise HTTPException(status_code=404, detail="volume nao encontrado")

    new_title = body.volume_title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="titulo do volume nao pode ser vazio")

    old_title = vol["volume_title"]
    if new_title == (old_title or "").strip():
        return vol  # nada mudou — evita rebuild a toa

    novel_id = vol["novel_id"]
    # Re-compoe o texto da capa por IA sobre a arte crua (sem custo). Volumes com
    # capa raspada/sem capa pulam isso — so o titulo interno do .epub muda.
    if vol["ai_cover"]:
        novel = ChapterCache().get_novel(novel_id)
        novel_title = (novel or {}).get("title") or ""
        status = await asyncio.to_thread(  # Pillow fora do event loop
            recompose_cover_text,
            novel_id=novel_id,
            old_title=old_title,
            new_title=new_title,
            novel_title=novel_title,
        )
        if status == "no_raw":
            raise HTTPException(
                status_code=409,
                detail="arte sem texto indisponivel — regenere a arte da capa antes de renomear",
            )

    vs.rename(volume_id, new_title)

    # Remonta o .epub do cache com o novo titulo (e a capa re-composta). Zero token.
    try:
        await rebuild_volume_epub(volume_id)
    except RebuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated = vs.get(volume_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="volume sumiu apos rebuild")
    return updated


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
