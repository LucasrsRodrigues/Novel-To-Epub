"""Pasta por novel + migracao da layout plana (EPUB homonimo entre novels)."""

from pathlib import Path

from app.config import settings
from app.db import models as orm
from app.db.cache import ChapterCache
from app.db.database import get_session
from app.db.volume_store import VolumeStore, novel_epub_dir
from app.models import NovelMeta


def _novel(slug: str) -> int:
    return ChapterCache().upsert_novel("x", slug, NovelMeta(title=slug, source_url=slug, chapters=[]))


def _save(vs: VolumeStore, novel_id: int, path: Path, start: int = 1) -> int:
    return vs.save_completed(
        novel_id=novel_id, source_url="u", volume_title="Volume 1", start=start, end=2,
        with_cover=False, ai_cover=False, translate_to=None, output_path=str(path),
        translation_failed=0,
    )


def test_same_volume_name_in_different_novels_gets_different_paths():
    a = novel_epub_dir(settings.output_dir, "novel-a") / "volume-1.epub"
    b = novel_epub_dir(settings.output_dir, "novel-b") / "volume-1.epub"
    assert a != b


def test_migrate_moves_flat_files_and_is_idempotent(tmp_path):
    settings.ensure_dirs()
    vs = VolumeStore()
    a, b = _novel("novel-a"), _novel("novel-b")
    flat = settings.output_dir / "volume-1.epub"
    flat.write_text("A")
    missing = settings.output_dir / "sumiu.epub"
    outside = tmp_path / "cli" / "cli.epub"
    v1, v2, v3 = _save(vs, a, flat), _save(vs, b, missing), _save(vs, b, outside, start=3)

    assert vs.migrate_flat_paths() == 2
    new = novel_epub_dir(settings.output_dir, "novel-a") / "volume-1.epub"
    assert vs.get(v1)["output_path"] == str(new) and new.read_text() == "A"
    assert not flat.exists()
    assert vs.get(v2)["output_path"].endswith("novel-b/sumiu.epub")
    assert vs.get(v3)["output_path"] == str(outside)  # fora de epubs/: intocado
    assert vs.migrate_flat_paths() == 0


def test_migrate_collision_gives_file_to_most_recent_volume():
    """Caso real: dois volumes de novels diferentes apontando pro mesmo arquivo."""
    settings.ensure_dirs()
    vs = VolumeStore()
    old_owner, new_owner = _novel("supreme-magus"), _novel("shadow-slave")
    shared = settings.output_dir / "volume-1-pt-BR.epub"
    shared.write_text("conteudo do shadow slave")
    v_old = _save(vs, old_owner, shared)
    v_new = _save(vs, new_owner, shared, start=5)
    with get_session() as s:  # garante a ordem temporal independente do relogio
        s.get(orm.GeneratedVolume, v_old).updated_at = s.get(orm.GeneratedVolume, v_new).updated_at.replace(year=2000)
        s.commit()

    vs.migrate_flat_paths()
    winner = Path(vs.get(v_new)["output_path"])
    loser = Path(vs.get(v_old)["output_path"])
    assert winner.parent.name == "shadow-slave" and winner.read_text() == "conteudo do shadow slave"
    assert loser.parent.name == "supreme-magus" and not loser.exists()


def test_delete_last_volume_removes_empty_novel_dir():
    settings.ensure_dirs()
    vs = VolumeStore()
    path = novel_epub_dir(settings.output_dir, "novel-a") / "v.epub"
    path.parent.mkdir(parents=True)
    path.write_text("x")
    vid = _save(vs, _novel("novel-a"), path)
    vs.delete(vid)
    assert not path.parent.exists()
    assert settings.output_dir.exists()
