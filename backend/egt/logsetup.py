"""Logging com arquivo rotativo na pasta de configuração. / Rotating file logging."""
from __future__ import annotations

import logging
import logging.handlers
import re
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

# chaves de API nunca vão para o log, nem por engano (ex.: texto de exceção de biblioteca)
SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                       # Google / Gemini
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),                      # estilo OpenAI
    re.compile(r"(?i)((?:api[_-]?key|token|x-goog-api-key|ocp-apim-subscription-key)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;]{8,}"),
]


def redact(text: str) -> str:
    for rx in SECRET_PATTERNS:
        text = rx.sub(lambda m: (m.group(1) if m.groups() else "") + "[chave removida]", text)
    return text


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            red = redact(msg)
            if red != msg:
                record.msg, record.args = red, ()
            if record.exc_info and record.exc_info[1] is not None:
                record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
                record.exc_info = None
        except Exception:  # pragma: no cover
            pass
        return True


_redact = RedactFilter()


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
            fh.addFilter(_redact)
            root.addHandler(fh)
        except OSError:
            pass
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.addFilter(_redact)
    root.addHandler(sh)
    ring.setFormatter(fmt)
    ring.addFilter(_redact)
    root.addHandler(ring)
    for noisy in ("urllib3", "PIL", "asyncio", "matplotlib"):  # bibliotecas barulhentas
        logging.getLogger(noisy).setLevel(logging.WARNING)


def tail_log(n: int = 60) -> str:
    """Últimas n linhas do arquivo de log (ou do buffer em memória)."""
    try:
        text = paths.log_file().read_text(encoding="utf-8", errors="replace")
        return redact("\n".join(text.splitlines()[-n:]))     # também limpa logs antigos (antes do filtro)
    except OSError:
        return redact("\n".join(list(ring.lines)[-n:]))
