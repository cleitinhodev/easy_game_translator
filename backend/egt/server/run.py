"""Inicialização do servidor: porta livre aleatória em 127.0.0.1 + token da sessão."""
from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import sys
import threading

from .. import APP_NAME, __version__, logsetup


def _watch_stdin(server) -> None:
    """Se o Electron morrer (stdin fecha), encerra o backend para não ficar órfão."""
    try:
        while sys.stdin and sys.stdin.read(1024):
            pass
    except Exception:
        return
    logging.getLogger("egt").info("stdin fechado; encerrando")
    server.should_exit = True


def main() -> int:
    logsetup.setup_logging()
    log = logging.getLogger("egt")
    from ..capture.screen import enable_dpi_awareness
    enable_dpi_awareness()
    import uvicorn

    from ..app import AppController
    from .app import create_app

    token = os.environ.get("EGT_TOKEN") or secrets.token_urlsafe(32)
    port = int(os.environ.get("EGT_PORT", "0") or 0)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(64)
    port = sock.getsockname()[1]

    ctrl = AppController()
    if os.environ.get("EGT_DEMO") == "1":      # só para testes de UI/screenshots
        from .. import demo
        demo.install(ctrl)
        log.warning("MODO DEMONSTRAÇÃO ativo (captura e tradução sintéticas)")
    app = create_app(ctrl, token)
    config = uvicorn.Config(app, log_level="warning", ws="auto", access_log=False, lifespan="on")
    server = uvicorn.Server(config)
    app.state.server = server
    log.info("%s v%s backend em 127.0.0.1:%d (Python %s)", APP_NAME, __version__, port, sys.version.split()[0])

    orig_startup = server.startup

    async def startup(sockets=None):
        await orig_startup(sockets=sockets)
        ready = {"port": port, "version": __version__, "pid": os.getpid()}
        if not os.environ.get("EGT_TOKEN"):
            ready["token"] = token          # modo manual: sem Electron para informar o token
        if sys.stdout is not None:
            print("EGT_READY " + json.dumps(ready), flush=True)

    server.startup = startup  # type: ignore[method-assign]
    if os.environ.get("EGT_WATCH_STDIN", "1") == "1" and sys.stdin is not None and not sys.stdin.isatty():
        threading.Thread(target=_watch_stdin, args=(server,), name="egt-stdin", daemon=True).start()
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    return 0
