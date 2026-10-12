"""Envio pro Kindle: as 3 rotas usam o mesmo helper (app.api.deps)."""

import pytest
from starlette.testclient import TestClient

import app.api.deps as deps
from app.api.server import create_app
from app.db.cache import ChapterCache
from app.db.settings_store import SettingsStore
from app.db.volume_store import VolumeStore
from app.models import NovelMeta


@pytest.fixture
def sent(monkeypatch):
    calls = []

    async def fake_send(path, **kw):
        calls.append((path, kw))

    monkeypatch.setattr(deps, "send_epub_to_kindle", fake_send)
    return calls


@pytest.fixture
def volume(tmp_path):
    novel_id = ChapterCache().upsert_novel("x", "n", NovelMeta(title="N", source_url="u", chapters=[]))
    epub = tmp_path / "v.epub"
    epub.write_bytes(b"epub")
    vid = VolumeStore().save_completed(
        novel_id=novel_id, source_url="u", volume_title="V1", start=1, end=2, with_cover=False,
        ai_cover=False, translate_to=None, output_path=str(epub), translation_failed=0,
    )
    return novel_id, vid, epub


def test_missing_config_is_400_listing_fields(volume, sent):
    _, vid, _ = volume
    with TestClient(create_app()) as c:
        r = c.post(f"/api/volumes/{vid}/kindle")
    assert r.status_code == 400
    assert "smtp_host" in r.json()["detail"] and "kindle_email" in r.json()["detail"]
    assert sent == []


def test_volume_and_bulk_send_use_saved_config(volume, sent):
    novel_id, vid, epub = volume
    SettingsStore().update({"smtp_host": "smtp.x", "smtp_from": "eu@x", "kindle_email": "k@kindle.com",
                            "smtp_user": "eu", "smtp_password": "pw"})
    with TestClient(create_app()) as c:
        r1 = c.post(f"/api/volumes/{vid}/kindle")
        r2 = c.post(f"/api/library/{novel_id}/kindle-all")
    assert r1.json() == {"status": "sent", "to": "k@kindle.com"}
    assert r2.json()["sent"] == 1 and r2.json()["total"] == 1
    path, kw = sent[0]
    assert path == str(epub) and kw["host"] == "smtp.x" and kw["to"] == "k@kindle.com" and kw["password"] == "pw"
