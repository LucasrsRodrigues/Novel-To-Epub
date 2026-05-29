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
from app.db.volume_store import VolumeStore
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
    cover_style: str | None = None  # id do estilo de arte (None = IA decide)
    # Quando setado, este job NAO baixa/traduz — so regera a capa do volume e
    # recompila o .epub do cache (caminho leve "so capa"). None = job normal.
    cover_only_volume_id: int | None = None
    # Volume a remover (registro + .epub) depois que este job gerar o novo .epub
    # com sucesso. Usado pra "traduzir no lugar" (substitui o original sem traducao).
    replace_volume_id: int | None = None
    status: str = "queued"  # queued | running | done | error | cancelled
    stage: str = "idle"      # idle | meta | download | translate | cover
    translation_failed: int = 0  # caps que ficaram em EN por falha
    # Detalhe por cap que falhou: TranslationFailure(chapter, title, reason).
    # Preenchido por on_complete; vazio enquanto o job nao terminou.
    translation_failures: list[TranslationFailure] = field(default_factory=list)
    # Motivo da falha de capa por IA (rate-limit, sem key...). None = capa ok ou
    # nao pedida. Preenchido por on_complete; UI mostra pro usuario.
    cover_error: str | None = None
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
            cover_error=self.cover_error,
            volume_id=self.volume_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class JobManager:
    def __init__(self, *, workers: int = 1) -> None:
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        # Task asyncio do _run em andamento por job_id. Permite cancel granular
        # sem derrubar o worker inteiro. Limpa em _worker quando _run termina.
        self._running: dict[str, asyncio.Task] = {}
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
            cover_style=req.cover_style,
            replace_volume_id=req.replace_volume_id,
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

    def enqueue_cover_regen(self, vol: dict, cover_style: str | None) -> Job:
        """Enfileira um job LEVE de regerar só a capa (sem baixar/traduzir).
        ``vol`` e o dict do VolumeStore (campos só pra exibir o card no Downloads)."""
        job = Job(
            id=uuid.uuid4().hex[:12],
            url=vol["source_url"],
            start=vol["start"],
            end=vol["end"],
            with_cover=vol["with_cover"],
            translate_to=vol["translate_to"],
            volume_title=vol["volume_title"],
            ai_cover=True,
            cover_style=cover_style,
            cover_only_volume_id=vol["id"],
        )
        self._jobs[job.id] = job
        self._queue.put_nowait(job.id)
        self._publish("queued", job)
        log.info("cover_regen_enqueued", id=job.id, volume_id=vol["id"], style=cover_style)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def cancel(self, job_id: str) -> Job | None:
        """Cancela um job 'queued' (sem efeito) ou 'running' (cancela a task).

        Idempotente: cancelar um job ja terminado/cancelado retorna o job sem
        mexer no estado. Pra running, o asyncio.Task.cancel() levanta
        CancelledError dentro do _run; o except la cuida de marcar status.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status in ("done", "error", "cancelled"):
            return job
        if job.status == "queued":
            # _worker filtra no consume — basta marcar.
            job.status = "cancelled"
            self._touch(job)
            self._publish("cancelled", job)
            log.info("job_cancelled_queued", id=job.id)
            return job
        # running
        task = self._running.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        return job

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
            # Job pode ter sido cancelado enquanto estava na fila — pula sem rodar.
            if job is None or job.status == "cancelled":
                self._queue.task_done()
                continue
            # Encapsula _run numa task pra permitir cancel granular via cancel().
            task = asyncio.create_task(self._run(job))
            self._running[job_id] = task
            try:
                await task
            except asyncio.CancelledError:
                # Cancelamento veio do cancel() — _run propagou. Marca status
                # apenas se o job ja nao esta em estado terminal.
                if job.status not in ("done", "error", "cancelled"):
                    job.status = "cancelled"
                    self._touch(job)
                    self._publish("cancelled", job)
                log.info("job_cancelled_running", id=job.id)
            except Exception as exc:  # rede de seguranca
                job.status = "error"
                job.error = str(exc)
                self._touch(job)
                self._publish("error", job)
                log.warning("job_failed", id=job.id, error=str(exc))
            finally:
                self._running.pop(job_id, None)
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
            job.cover_error = stats.get("cover_error") or None
            vid = stats.get("volume_id")
            if isinstance(vid, int):
                job.volume_id = vid

        if job.cover_only_volume_id is not None:
            # Caminho leve: regera SO a capa + recompila do cache (sem download/traducao).
            from app.rebuild import regenerate_cover_only

            job.stage = "cover"
            path = await regenerate_cover_only(
                job.cover_only_volume_id,
                cover_style=job.cover_style,
                progress=on_progress,
                on_complete=on_complete,
            )
            job.output_path = str(path)
            job.status = "done"
            self._touch(job)
            self._publish("done", job)
            log.info("cover_regen_done", id=job.id, path=str(path))
            return

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
            cover_style=job.cover_style,
            on_complete=on_complete,
        )
        job.output_path = str(path)
        # Traduzir no lugar (item 1): apaga o volume antigo (sem traducao) so
        # DEPOIS que o novo nasceu ok. So apaga se o novo realmente foi persistido
        # (volume_id setado por on_complete) e e outro registro — o sufixo de
        # idioma garante output_path diferente, entao nunca apaga a si mesmo.
        if (
            job.replace_volume_id is not None
            and job.volume_id
            and job.replace_volume_id != job.volume_id
        ):
            try:
                VolumeStore().delete(job.replace_volume_id, delete_file=True)
                log.info(
                    "volume_replaced", old=job.replace_volume_id, new=job.volume_id
                )
            except Exception as exc:  # nao derruba o job por causa da limpeza
                log.warning(
                    "volume_replace_failed",
                    id=job.replace_volume_id,
                    error=str(exc),
                )
        job.status = "done"
        self._touch(job)
        self._publish("done", job)
        log.info("job_done", id=job.id, path=str(path))
