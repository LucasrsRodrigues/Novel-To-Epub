"""Token da API local (gerado pelo Electron a cada abertura do app).

O backend escuta em 127.0.0.1 numa porta aleatoria, mas isso nao basta: qualquer
pagina aberta no navegador consegue varrer portas de localhost e chamar a API
(CORS nao impede requests "simples"). Sem token, um site malicioso podia trocar o
smtp_host pelo servidor dele e disparar "enviar pro Kindle" — o backend logava
la com a senha SMTP salva.

Com ``NOVEL_API_TOKEN`` definido, toda request HTTP e WebSocket precisa do token,
no header ``X-Api-Token`` ou na query ``?token=`` (``<img>``, ``<a download>`` e
WebSocket nao mandam header). Sem a env (CLI ``serve`` manual, dev no browser) a
API fica aberta como antes.
"""

from __future__ import annotations

import hmac
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

# Pingado pelo main do Electron antes de ter janela; so devolve status/versao.
_PUBLIC_PATHS = {"/api/health"}


class ApiTokenMiddleware:
    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self.token = token or None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            self.token is None
            or scope["type"] not in ("http", "websocket")
            or scope["path"] in _PUBLIC_PATHS
            or self._authorized(scope)
        ):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            # Fechar antes do accept → o servidor responde 403 ao handshake.
            await send({"type": "websocket.close", "code": 4401})
            return
        body = b'{"detail":"token da API ausente ou invalido"}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    def _authorized(self, scope: Scope) -> bool:
        sent = None
        for name, value in scope.get("headers") or []:
            if name == b"x-api-token":
                sent = value.decode("latin-1")
                break
        if sent is None:
            qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            sent = (qs.get("token") or [None])[0]
        return sent is not None and hmac.compare_digest(sent, self.token)
