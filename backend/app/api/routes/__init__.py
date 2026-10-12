"""Rotas REST da API, uma por area (antes: um routes.py de ~1000 linhas).

``router`` agrega todos sob ``/api`` — e o que o server inclui.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    chapters,
    covers,
    downloads,
    library,
    system,
    usage,
    volumes,
)

router = APIRouter(prefix="/api")
for _module in (system, downloads, library, volumes, covers, chapters, usage):
    router.include_router(_module.router)
