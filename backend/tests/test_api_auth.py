"""Token da API local + WebSocket de progresso."""

import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.server import create_app
from app.config import settings


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "s3cret")
    app = create_app()
    with TestClient(app) as c:
        yield c, app


def test_requests_need_token(client):
    c, _ = client
    assert c.get("/api/settings").status_code == 401
    assert c.get("/api/settings", headers={"X-Api-Token": "errado"}).status_code == 401
    assert c.put("/api/settings", json={"smtp_host": "evil.com"}).status_code == 401
    assert c.get("/api/settings", headers={"X-Api-Token": "s3cret"}).status_code == 200
    assert c.get("/api/settings?token=s3cret").status_code == 200
    assert c.get("/api/health").status_code == 200  # publico


def test_cors_preflight_and_401_readable(client):
    c, _ = client
    pre = c.options(
        "/api/settings",
        headers={"Origin": "null", "Access-Control-Request-Method": "PUT",
                 "Access-Control-Request-Headers": "x-api-token"},
    )
    assert pre.status_code == 200
    r = c.get("/api/settings", headers={"Origin": "null"})
    assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == "*"


def test_websocket_needs_token(client):
    c, _ = client
    with pytest.raises(WebSocketDisconnect) as info:
        with c.websocket_connect("/ws/progress"):
            pass
    assert info.value.code == 4401


def test_websocket_delivers_events_and_unsubscribes_on_close(client):
    c, app = client
    hub = app.state.jobs.hub
    with c.websocket_connect("/ws/progress?token=s3cret") as ws:
        time.sleep(0.1)
        assert len(hub._subs) == 1
        hub.publish({"event": "teste"})
        assert ws.receive_json() == {"event": "teste"}
    time.sleep(0.3)
    assert len(hub._subs) == 0


def test_no_token_configured_keeps_api_open():
    with TestClient(create_app()) as c:
        assert c.get("/api/settings").status_code == 200
