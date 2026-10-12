"""Persistencia de volumes EPUB gerados (lista da biblioteca por novel)."""

from __future__ import annotations

from pathlib import Path

from slugify import slugify
from sqlalchemy import select

from app.config import settings
from app.db import models as orm
from app.db.database import get_session, init_db
from app.logging_conf import get_logger

log = get_logger("volume_store")


def novel_epub_dir(output_dir: Path, novel_slug: str) -> Path:
    """Pasta dos .epub de uma novel: ``<output_dir>/<slug>/``.

    Cada novel tem a sua pasta pra que volumes com o mesmo nome ("Volume 1")
    de novels diferentes nao gravem no mesmo arquivo — antes um sobrescrevia o
    outro, e apagar um volume apagava o livro da outra novel.
    """
    return output_dir / (slugify(novel_slug) or "novel")


class VolumeStore:
    def __init__(self) -> None:
        init_db()

    def save_completed(
        self,
        *,
        novel_id: int,
        source_url: str,
        volume_title: str | None,
        start: int,
        end: int | None,
        with_cover: bool,
        ai_cover: bool,
        translate_to: str | None,
        output_path: str,
        translation_failed: int,
        skip_chapters: list[int] | None = None,
    ) -> int:
        """Upsert por (novel_id, output_path). Devolve o id do volume."""
        with get_session() as s:
            row = s.scalar(
                select(orm.GeneratedVolume).where(
                    orm.GeneratedVolume.novel_id == novel_id,
                    orm.GeneratedVolume.output_path == output_path,
                )
            )
            if row is None:
                row = orm.GeneratedVolume(
                    novel_id=novel_id,
                    output_path=output_path,
                    source_url=source_url,
                )
                s.add(row)
            row.volume_title = volume_title
            row.start_chapter = start
            row.end_chapter = end
            row.with_cover = with_cover
            row.ai_cover = ai_cover
            row.translate_to = translate_to
            row.translation_failed = translation_failed
            row.skip_chapters = ",".join(str(i) for i in (skip_chapters or []))
            row.source_url = source_url
            s.commit()
            s.refresh(row)
            return row.id

    def rename(self, volume_id: int, new_title: str | None) -> bool:
        """Troca so o ``volume_title`` do volume. Devolve False se nao existe.

        Mantem o ``output_path`` (arquivo no disco nao se move); o titulo interno
        do .epub e atualizado no rebuild subsequente, que le este novo valor.
        """
        with get_session() as s:
            row = s.get(orm.GeneratedVolume, volume_id)
            if row is None:
                return False
            row.volume_title = new_title
            s.commit()
            return True

    def list_for_novel(self, novel_id: int) -> list[dict]:
        """Volumes gerados desta novel, mais novos primeiro."""
        with get_session() as s:
            rows = s.scalars(
                select(orm.GeneratedVolume)
                .where(orm.GeneratedVolume.novel_id == novel_id)
                .order_by(orm.GeneratedVolume.created_at.desc())
            ).all()
            return [_to_dict(r) for r in rows]

    def get(self, volume_id: int) -> dict | None:
        with get_session() as s:
            row = s.get(orm.GeneratedVolume, volume_id)
            return _to_dict(row) if row else None

    def delete(self, volume_id: int, *, delete_file: bool = True) -> bool:
        """Remove o registro do volume e, opcionalmente, o .epub do disco.

        Devolve True se removeu, False se o volume nao existia. A remocao do
        arquivo e best-effort (nao falha se o .epub ja sumiu). Cache de
        capitulos/traducao/capa NAO e tocado — so o volume gerado.
        """
        with get_session() as s:
            row = s.get(orm.GeneratedVolume, volume_id)
            if row is None:
                return False
            path = row.output_path
            s.delete(row)
            s.commit()
        if delete_file and path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass  # arquivo travado/permissao — registro ja foi embora
            _remove_if_empty_novel_dir(Path(path).parent)
        return True

    def migrate_flat_paths(self) -> int:
        """Move .epubs da layout antiga (soltos em ``output_dir``) pra pasta da
        novel (``output_dir/<slug>/``) e atualiza ``output_path``. Idempotente.

        So mexe em volumes cujo arquivo estava direto em ``settings.output_dir``
        (saidas da CLI em outras pastas ficam como estao). Se o arquivo sumiu do
        disco, so o caminho e atualizado — re-capturar o volume volta a casar
        com o mesmo registro. Devolve quantos registros foram migrados.
        """
        root = settings.output_dir.resolve()
        migrated = 0
        with get_session() as s:
            rows = s.execute(
                select(orm.GeneratedVolume, orm.Novel.slug)
                .join(orm.Novel, orm.Novel.id == orm.GeneratedVolume.novel_id)
                # Mais recente primeiro: se o bug ja fez dois volumes apontarem pro
                # mesmo arquivo, quem gravou por ultimo e o dono do conteudo e leva
                # o .epub; o outro fica com o path na pasta dele, sem arquivo
                # (precisa "Recompilar" — o conteudo dele ja tinha sido sobrescrito).
                .order_by(orm.GeneratedVolume.updated_at.desc(), orm.GeneratedVolume.id.desc())
            ).all()
            for row, slug in rows:
                old = Path(row.output_path)
                if old.parent.resolve() != root:
                    continue
                new = novel_epub_dir(settings.output_dir, slug) / old.name
                if old.exists():
                    if new.exists():
                        # Ja existe na pasta nova (ex.: outra novel com o mesmo
                        # nome gravou antes da correcao) — nao sobrescreve.
                        log.warning("volume_migrate_conflict", old=str(old), new=str(new))
                        continue
                    new.parent.mkdir(parents=True, exist_ok=True)
                    old.rename(new)
                row.output_path = str(new)
                migrated += 1
            s.commit()
        if migrated:
            log.info("volume_paths_migrated", count=migrated)
        return migrated


def _remove_if_empty_novel_dir(folder: Path) -> None:
    """Apaga a pasta da novel quando o ultimo .epub dela sai (nunca a raiz)."""
    try:
        if folder.resolve() != settings.output_dir.resolve() and not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        pass


def _to_dict(row: orm.GeneratedVolume) -> dict:
    return {
        "id": row.id,
        "novel_id": row.novel_id,
        "volume_title": row.volume_title,
        "start": row.start_chapter,
        "end": row.end_chapter,
        "with_cover": row.with_cover,
        "ai_cover": row.ai_cover,
        "translate_to": row.translate_to,
        "output_path": row.output_path,
        "translation_failed": row.translation_failed,
        "skip_chapters": [
            int(x) for x in (row.skip_chapters or "").split(",") if x.strip().lstrip("-").isdigit()
        ],
        "source_url": row.source_url,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
