"""Rota legada POST /downloads/{job_id}/regenerate-cover."""

import pytest
from starlette.testclient import TestClient

import app.api.jobs as jobs_mod
from app.api.server import create_app
from app.db.cache import ChapterCache
from app.db.cover_cache import CoverCache
from app.db.volume_store import VolumeStore
from app.models import NovelMeta


@pytest.fixture
def setup(monkeypatch):
    novel_id = ChapterCache().upsert_novel(
        "x", "n", NovelMeta(title="N", source_url="https://site/n", chapters=[])
    )
    vid = VolumeStore().save_completed(
        novel_id=novel_id, source_url="https://site/n", volume_title="Volume 1", start=2, end=9,
        with_cover=True, ai_cover=True, translate_to="pt-BR", output_path="/tmp/v1.epub",
        translation_failed=0, skip_chapters=[1],
    )
    calls = []

    def fake_regen(self, vol, style):
        calls.append((vol, style))
        return jobs_mod.Job(id="regen", url=vol["source_url"], start=vol["start"], end=vol["end"],
                            with_cover=True, cover_only_volume_id=vol["id"])

    def no_delete(*a, **kw):
        raise AssertionError("a capa nao pode ser apagada antes de gerar a nova")

    monkeypatch.setattr(jobs_mod.JobManager, "enqueue_cover_regen", fake_regen)
    monkeypatch.setattr(CoverCache, "delete", no_delete)
    app = create_app()
    with TestClient(app) as c:
        yield c, app.state.jobs, vid, calls


def _job(jobs, **kw):
    j = jobs_mod.Job(id=kw.pop("id"), url="https://site/n", start=2, end=9, with_cover=True,
                     volume_title="Volume 1", translate_to="pt-BR", status="done", **kw)
    jobs._jobs[j.id] = j
    return j


def test_delegates_to_cover_only_regen_keeping_skip_chapters(setup):
    c, jobs, vid, calls = setup
    _job(jobs, id="j1", volume_id=vid)
    r = c.post("/api/downloads/j1/regenerate-cover", json={"cover_style": "dark-fantasy"})
    assert r.status_code == 201
    vol, style = calls[0]
    assert vol["id"] == vid and vol["skip_chapters"] == [1] and style == "dark-fantasy"


def test_old_job_without_volume_id_matches_by_title_and_language(setup):
    c, jobs, vid, calls = setup
    _job(jobs, id="j2")
    assert c.post("/api/downloads/j2/regenerate-cover").status_code == 201
    assert calls[0][0]["id"] == vid


def test_job_without_volume_is_409(setup):
    c, jobs, _, calls = setup
    j = _job(jobs, id="j3")
    j.volume_title = "Outro volume"
    assert c.post("/api/downloads/j3/regenerate-cover").status_code == 409
    assert calls == []
