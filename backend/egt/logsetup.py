"""Logging com arquivo rotativo na pasta de configuração. / Rotating file logging."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from collections import deque

from . import paths

_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_configured = False


class RingHandler(logging.Handler):
    """Guarda as últimas linhas em memória (para a aba Reportar Erros)."""

    def __init__(self, capacity: int = 300):
        super().__init__()
        self.lines: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # pragma: no cover
            pass


ring = RingHandler()


def setup_logging(level: int = logging.INFO, to_file: bool = True) -> None:
    """Configura o logger raiz uma única vez. / Configure root logger once."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter(_FMT)
    if to_file:
        try:
            fh = logging.handlers.RotatingFileHandler(
                paths.log_file(), maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            pass
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    ring.setFormatter(fmt)
    root.addHandler(ring)
    for noisy in ("urllib3", "PIL", "asyncio", "matplotlib"):  # bibliotecas barulhentas
        logging.getLogger(noisy).setLevel(logging.WARNING)


def tail_log(n: int = 60) -> str:
    """Últimas n linhas do arquivo de log (ou do buffer em memória)."""
    try:
        text = paths.log_file().read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-n:])
    except OSError:
        return "\n".join(list(ring.lines)[-n:])
