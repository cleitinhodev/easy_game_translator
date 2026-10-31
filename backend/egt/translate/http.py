"""Ajudantes HTTP comuns aos tradutores online: sessão com User-Agent, tempo-limite, intervalo mínimo
entre pedidos (por motor, global ao processo) e mapeamento de erros HTTP → códigos que a interface traduz.

Nada aqui registra o texto enviado nem chaves: só o nome do motor e o código do erro.
"""
from __future__ import annotations

import threading
import time

from .base import RateLimited, TranslationError

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")

_local = threading.local()
_last: dict[str, float] = {}
_last_lock = threading.Lock()
MAX_THROTTLE_WAIT = 3.0


def session():
    """Uma requests.Session por thread (reaproveita conexões TLS; não compartilha estado entre threads)."""
    s = getattr(_local, "s", None)
    if s is None:
        import requests
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
        s.trust_env = True
        _local.s = s
    return s


def throttle(key: str, min_interval: float) -> None:
    """Garante `min_interval` segundos entre pedidos ao mesmo serviço (vale para todas as threads)."""
    if min_interval <= 0:
        return
    with _last_lock:
        now = time.monotonic()
        wait = _last.get(key, 0.0) + min_interval - now
        wait = max(0.0, min(wait, MAX_THROTTLE_WAIT))
        _last[key] = now + wait
    if wait > 0:
        time.sleep(wait)


def reset_throttle() -> None:
    with _last_lock:
        _last.clear()


def request(name: str, method: str, url: str, *, timeout: float = 8.0, allow_redirects: bool = False, **kw):
    """Faz o pedido; erros de rede viram TranslationError(network/timeout). Não segue redirecionamentos
    (um 302 para a página de 'sorry'/login é tratado como bloqueio)."""
    import requests
    try:
        return session().request(method, url, timeout=timeout, allow_redirects=allow_redirects, **kw)
    except requests.Timeout as exc:
        raise TranslationError(f"{name}: tempo esgotado", "timeout") from exc
    except requests.RequestException as exc:
        raise TranslationError(f"{name}: sem conexão ({type(exc).__name__})", "network") from exc


def retry_after(r, default: float) -> float:
    try:
        return max(1.0, min(float(r.headers.get("Retry-After", default)), 3600.0))
    except (TypeError, ValueError):
        return default


def check(name: str, r, *, rate_wait: float = 60.0, ok: tuple = (200,)) -> None:
    """Levanta o erro certo para respostas não-OK. Nunca inclui o corpo (pode ecoar o texto ou a chave)."""
    st = r.status_code
    if st in ok:
        return
    if st == 429:
        raise RateLimited(f"{name}: muitas requisições (HTTP 429)", retry_after=retry_after(r, rate_wait))
    if st in (401, 403):
        raise TranslationError(f"{name}: chave inválida ou sem permissão (HTTP {st})", "bad_key")
    if st == 456:
        raise RateLimited(f"{name}: cota esgotada (HTTP 456)", retry_after=3600, code="quota")
    if st in (301, 302, 303, 307, 308):
        raise RateLimited(f"{name}: bloqueado temporariamente pelo serviço (HTTP {st})", retry_after=rate_wait, code="blocked")
    if st >= 500:
        raise TranslationError(f"{name}: servidor indisponível (HTTP {st})", "server")
    raise TranslationError(f"{name}: erro HTTP {st}", "http")


def json_of(name: str, r):
    try:
        return r.json()
    except ValueError as exc:
        raise TranslationError(f"{name}: resposta inválida", "bad_response") from exc


def clean_url(url: str) -> str | None:
    """Só http(s) com host; sem credenciais embutidas. None se inválida."""
    import urllib.parse
    url = (url or "").strip().rstrip("/")
    if not url:
        return None
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        return None
    return url
