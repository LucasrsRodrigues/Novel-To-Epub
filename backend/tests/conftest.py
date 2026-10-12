"""Fixtures compartilhadas.

Todo teste roda com ``settings.data_dir`` num diretorio temporario e um engine
SQLite novo — o modulo ``app.db.database`` guarda o engine num global, entao
sem resetar ele os testes escreveriam no banco do teste anterior (ou no de dev).
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.db import database


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "api_token", None)
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_SessionFactory", None)
    yield tmp_path
    if database._engine is not None:
        database._engine.dispose()
