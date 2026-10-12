"""JobManager: fila, cancel/resume, shutdown — com o download simulado."""

import asyncio
from pathlib import Path

import pytest

import app.api.jobs as jobs_mod
from app.api.schemas import DownloadRequest


@pytest.fixture
def fake_download(monkeypatch):
    calls: list[str] = []
    gate = asyncio.Event()

    async def fake(url, **kw):
        calls.append(url)
        if "slow" in url:
            await asyncio.sleep(3600)
        if "gate" in url:
            await gate.wait()
        kw["on_complete"]({"volume_id": 1})
        return Path("/tmp/x.epub")

    monkeypatch.setattr(jobs_mod, "download_to_epub", fake)
    return calls, gate


def test_cancel_queued_then_resume_runs_once(fake_download):
    calls, gate = fake_download

    async def main():
        m = jobs_mod.JobManager(workers=1)
        await m.start()
        m.enqueue(DownloadRequest(url="https://x/gate-a"))
        b = m.enqueue(DownloadRequest(url="https://x/b"))
        await asyncio.sleep(0.05)
        m.cancel(b.id)
        m.resume(b.id)
        gate.set()
        await asyncio.sleep(0.2)
        status = m.get(b.id).status
        await m.stop()
        return status

    assert asyncio.run(main()) == "done"
    assert calls.count("https://x/b") == 1


def test_resume_clears_previous_results(fake_download):
    async def main():
        m = jobs_mod.JobManager(workers=1)
        await m.start()
        j = m.enqueue(DownloadRequest(url="https://x/slow"))
        await asyncio.sleep(0.05)
        m.cancel(j.id)
        await asyncio.sleep(0.05)
        j.cover_error, j.volume_id, j.output_path = "velho", 9, "/velho.epub"
        m.resume(j.id)
        snapshot = (j.cover_error, j.volume_id, j.output_path)
        await m.stop()
        return snapshot

    assert asyncio.run(main()) == (None, None, None)


def test_user_cancel_running_keeps_worker_alive(fake_download):
    async def main():
        m = jobs_mod.JobManager(workers=1)
        await m.start()
        a = m.enqueue(DownloadRequest(url="https://x/slow"))
        b = m.enqueue(DownloadRequest(url="https://x/fast"))
        await asyncio.sleep(0.05)
        m.cancel(a.id)
        await asyncio.sleep(0.1)
        result = (m.get(a.id).status, m.get(b.id).status)
        await m.stop()
        return result

    assert asyncio.run(main()) == ("cancelled", "done")


def test_stop_with_running_job_is_quick_and_marks_interrupted(fake_download):
    async def main():
        m = jobs_mod.JobManager(workers=1)
        await m.start()
        j = m.enqueue(DownloadRequest(url="https://x/slow"))
        await asyncio.sleep(0.05)
        await asyncio.wait_for(m.stop(), timeout=1)  # antes: travava pra sempre
        m2 = jobs_mod.JobManager(workers=1)
        await m2.start()  # re-hidrata a intencao persistida
        status = m2.get(j.id).status
        resumable = m2.resume(j.id) is not None
        await m2.stop()
        return status, resumable

    assert asyncio.run(main()) == ("interrupted", True)
