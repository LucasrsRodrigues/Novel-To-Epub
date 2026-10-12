"""Aplicacao FastAPI: monta REST + WebSocket e gerencia o ciclo do JobManager."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.auth import ApiTokenMiddleware
from app.api.jobs import JobManager
from app.api.routes import router
from app.config import settings
from app.db.volume_store import VolumeStore
from app.logging_conf import configure_logging, get_logger

log = get_logger("server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Antes dos jobs: re-hidratar capturas usa os mesmos output_path.
    try:
        VolumeStore().migrate_flat_paths()
    except Exception as exc:  # migracao nunca impede o app de subir
        log.warning("volume_migrate_failed", error=str(exc))
    app.state.jobs = JobManager(workers=1)
    await app.state.jobs.start()
    log.info("api_started")
    try:
        yield
    finally:
        await app.state.jobs.stop()
        log.info("api_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Novel Scraper to EPUB", version=__version__, lifespan=lifespan)

    # Token antes do CORS: o ultimo middleware adicionado fica por fora, entao o
    # CORS responde o preflight (que nao leva o header do token) e poe os headers
    # CORS ate no 401 — o renderer consegue ler o motivo.
    app.add_middleware(ApiTokenMiddleware, token=settings.api_token)

    # Electron/dev: libera CORS (app local)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.websocket("/ws/progress")
    async def ws_progress(ws: WebSocket) -> None:
        await ws.accept()
        queue = app.state.jobs.hub.subscribe()
        try:
            while True:
                event = await queue.get()
                await ws.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            app.state.jobs.hub.unsubscribe(queue)

    return app


app = create_app()
