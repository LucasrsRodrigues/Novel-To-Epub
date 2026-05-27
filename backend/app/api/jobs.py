"""Fila assincrona de downloads + estado dos jobs.

Jobs ficam em memoria (sao efemeros; o que persiste e o cache/biblioteca).
Por padrao 1 worker consome a fila, serializando os downloads para respeitar
o rate limit. Cada transicao de estado e publicada no hub (WebSocket).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.api.hub import ConnectionHub
from app.api.schemas import DownloadRequest, JobStatus, TranslationFailure
from app.logging_conf import get_logger
from app.models import NovelMeta
from app.orchestrator import download_to_epub

log = get_logger("jobs")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    id: str
    url: str
    start: int
    end: int | None
    with_cover: bool
    translate_to: str | None = None
    volume_title: str | None = None
    ai_cover: bool = False
    status: str = "queued"  # queued | running | done | error
    stage: str = "idle"      # idle | download | translate | cover
    translation_failed: int = 0  # caps que ficaram em EN por falha
    # Detalhe por cap que falhou: TranslationFailure(chapter, title, reason).
    # Preenchido por on_complete; vazio enquanto o job nao terminou.
    translation_failures: list[TranslationFailure] = field(default_factory=list)
    # Id do GeneratedVolume persistido em SQLite (preenchido por on_complete).
    # UI usa pra chamar endpoints baseados em volume_id, que sobrevivem ao
    # restart do backend (jobs sao in-memory; volumes nao).
    volume_id: int | None = None
    done: int = 0
    total: int = 0
    title: str | None = None
    current: str | None = None
    output_path: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def to_status(self) -> JobStatus:
        return JobStatus(
            id=self.id,
            url=self.url,
            start=self.start,
            end=self.end,
            with_cover=self.with_cover,
            translate_to=self.translate_to,
            volume_title=self.volume_title,
            ai_cover=self.ai_cover,
            status=self.status,
            stage=self.stage,
            done=self.done,
            total=self.total,
            title=self.title,
            current=self.current,
            output_path=self.output_path,
            error=self.error,
            translation_failed=self.translation_failed,
            translation_failures=self.translation_failures,
            volume_id=self.volume_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class JobManager:
    def __init__(self, *, workers: int = 1) -> None:
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._n_workers = workers
        self.hub = ConnectionHub()

    # ---------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker(i)) for i in range(self._n_workers)
        ]
        log.info("jobmanager_started", workers=self._n_workers)

    async def stop(self) -> None:
        for t in self._workers:
            t.cancel()
        for t in self._workers:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._workers = []
        log.info("jobmanager_stopped")

    # ---------------------------------------------------------------------- api
    def enqueue(self, req: DownloadRequest) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            url=req.url,
            start=req.start,
            end=req.end,
            with_cover=req.with_cover,
            translate_to=req.translate_to,
            volume_title=req.volume_title,
            ai_cover=req.ai_cover,
        )
        self._jobs[job.id] = job
        self._queue.put_nowait(job.id)
        self._publish("queued", job)
        log.info(
            "job_enqueued",
            id=job.id,
            url=req.url,
            translate_to=req.translate_to,
            volume_title=req.volume_title,
        )
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    # ---------------------------------------------------------------- internals
    def _touch(self, job: Job) -> None:
        job.updated_at = _now()

    def _publish(self, event: str, job: Job) -> None:
        self.hub.publish(
            {"event": event, "job": job.to_status().model_dump(mode="json")}
        )

    async def _worker(self, n: int) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._jobs.get(job_id)
            if job is None:
                self._queue.task_done()
                continue
            try:
                await self._run(job)
            except Exception as exc:  # rede de seguranca
                job.status = "error"
                job.error = str(exc)
                self._touch(job)
                self._publish("error", job)
                log.warning("job_failed", id=job.id, error=str(exc))
            finally:
                self._queue.task_done()

    async def _run(self, job: Job) -> None:
        job.status = "running"
        job.stage = "download"
        self._touch(job)
        self._publish("running", job)

        def on_meta(meta: NovelMeta) -> None:
            job.title = meta.title
            self._touch(job)
            self._publish("progress", job)

        def on_progress(stage: str, done: int, total: int, title: str, from_cache: bool) -> None:
            # quando muda de fase (ex: download -> translate), reseta done/total visualmente
            job.stage = stage
            job.done = done
            job.total = total
            job.current = title
            self._touch(job)
            self._publish("progress", job)

        def on_complete(stats: dict) -> None:
            job.translation_failed = int(stats.get("translation_failed_count") or 0)
            # Converte os dicts crus do orchestrator pra TranslationFailure
            # (validacao Pydantic dropa chaves desconhecidas se vier algo torto).
            raw = stats.get("translation_failures") or []
            job.translation_failures = [
                TranslationFailure(**f) for f in raw
                if isinstance(f, dict)
            ]
            vid = stats.get("volume_id")
            if isinstance(vid, int):
                job.volume_id = vid

        path = await download_to_epub(
            job.url,
            start=job.start,
            end=job.end,
            with_cover=job.with_cover,
            progress=on_progress,
            on_meta=on_meta,
            translate_to=job.translate_to,
            volume_title=job.volume_title,
            ai_cover=job.ai_cover,
            on_complete=on_complete,
        )
        job.output_path = str(path)
        job.status = "done"
        self._touch(job)
        self._publish("done", job)
        log.info("job_done", id=job.id, path=str(path))
