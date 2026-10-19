"""Hub de eventos: threads do pipeline → fila asyncio → clientes WebSocket.

A thread `egt-events` lê os eventos do pipeline (queue.Queue) e publica no loop asyncio;
cada cliente tem sua própria fila limitada (cliente lento perde eventos antigos, nunca trava o resto).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Optional

log = logging.getLogger(__name__)


class _LogForwarder(logging.Handler):
    """Envia avisos/erros do log para a UI (aba Reportar Erros ao vivo)."""

    def __init__(self, hub: "EventHub"):
        super().__init__(level=logging.WARNING)
        self.hub = hub
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.hub.publish({"type": "log", "level": record.levelname, "line": self.format(record)})
        except Exception:
            pass


class EventHub:
    def __init__(self, controller, queue_size: int = 500):
        self.ctrl = controller
        self.queue_size = queue_size
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.clients: set[asyncio.Queue] = set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._log_handler = _LogForwarder(self)
        self.sent = 0

    # -- ciclo de vida
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._stop.clear()
        logging.getLogger().addHandler(self._log_handler)
        self._thread = threading.Thread(target=self._pump, name="egt-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        logging.getLogger().removeHandler(self._log_handler)
        if self._thread:
            self._thread.join(1.5)

    # -- clientes
    def add_client(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(self.queue_size)
        self.clients.add(q)
        return q

    def remove_client(self, q: asyncio.Queue) -> None:
        self.clients.discard(q)

    # -- publicação (qualquer thread)
    def publish(self, msg: dict[str, Any]) -> None:
        msg.setdefault("ts", round(time.time(), 3))
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._broadcast, msg)
        except RuntimeError:
            pass

    def _broadcast(self, msg: dict) -> None:
        payload = json.dumps(msg, ensure_ascii=False, default=str)
        self.sent += 1
        for q in list(self.clients):
            if q.full():
                try:
                    q.get_nowait()        # descarta o mais antigo
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(payload)

    # -- bomba de eventos
    def _pump(self) -> None:
        last_metrics = 0.0
        while not self._stop.is_set():
            try:
                events = self.ctrl.poll_events(timeout=0.2)
            except Exception:
                log.exception("erro ao ler eventos")
                time.sleep(0.5)
                continue
            for ev in events:
                self.publish({"type": ev.kind, "channel": ev.channel, "data": ev.data})
            now = time.monotonic()
            if now - last_metrics >= 1.0:
                last_metrics = now
                try:
                    if self.clients:
                        net = self.ctrl.check_network()
                        self.publish({"type": "metrics", "data": self.ctrl.metrics() | {"net": net}})
                except Exception:
                    log.exception("erro nas métricas")
