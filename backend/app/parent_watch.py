"""Encerra o backend quando o processo pai (Electron) morre sem avisar.

O Electron manda SIGTERM no quit normal. Mas se ele for morto (SIGKILL, crash,
force quit), ninguem avisa o backend — ele ficava orfao, segurando a porta e o
SQLite do userData ate o proximo boot (e a proxima abertura do app subia um
SEGUNDO backend no mesmo banco).

O Electron passa o proprio pid em ``NOVEL_PARENT_PID``. Uma thread daemon
confere a cada poucos segundos se o pai ainda e o nosso pai; quando nao e (o SO
re-parenteia o orfao pro init/launchd), manda SIGTERM pra si mesmo — o uvicorn
faz o shutdown normal (jobs viram 'interrupted', SQLite fecha limpo). Se mesmo
assim nao sair, ``os._exit``.

So POSIX: no Windows o ``getppid`` nao muda quando o pai morre.
"""

from __future__ import annotations

import os
import signal
import threading
import time

from app.logging_conf import get_logger

log = get_logger("parent_watch")

_POLL_S = 2.0
_GRACE_S = 10.0


def start_parent_watch() -> None:
    raw = os.environ.get("NOVEL_PARENT_PID")
    if not raw or os.name != "posix":
        return
    try:
        parent = int(raw)
    except ValueError:
        return
    threading.Thread(target=_watch, args=(parent,), name="parent-watch", daemon=True).start()


def _watch(parent: int) -> None:
    while os.getppid() == parent:
        time.sleep(_POLL_S)
    # Sinal ANTES de logar: com o pai morto, o pipe de stdout/stderr que ele lia
    # quebrou — o log levanta BrokenPipeError e mataria esta thread antes do kill.
    os.kill(os.getpid(), signal.SIGTERM)
    _try_log("parent_gone", parent=parent)
    time.sleep(_GRACE_S)
    _try_log("parent_gone_force_exit")
    os._exit(1)


def _try_log(event: str, **kw: object) -> None:
    try:
        log.warning(event, **kw)
    except Exception:
        pass
