"""Hub de broadcast para WebSocket.

Cada conexao WS se inscreve e recebe uma fila. ``publish`` e sincrono e
nao-bloqueante (``put_nowait``), entao pode ser chamado de dentro do callback
de progresso do orquestrador sem precisar de ``await``.
"""

from __future__ import annotations

import asyncio

from app.logging_conf import get_logger

log = get_logger("hub")


class ConnectionHub:
    def __init__(self, maxsize: int = 1000) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    @property
    def subscribers(self) -> int:
        return len(self._subs)

    def publish(self, event: dict) -> None:
        """Envia o evento para todos os inscritos (descarta se a fila encher)."""
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("ws_queue_full_dropping_event")
