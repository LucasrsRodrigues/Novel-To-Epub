"""Aplicacao FastAPI: monta REST + WebSocket e gerencia o ciclo do JobManager."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.jobs import JobManager
from app.api.routes import router
from app.logging_conf import configure_logging, get_logger

log = get_logger("server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
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
