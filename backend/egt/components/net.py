"""Acesso à rede dos componentes: HTTPS apenas, hosts oficiais em lista de permissão, redirecionamentos revalidados.

Nada aqui usa shell. Em testes/demonstração `allow_local=True` libera 127.0.0.1 (http) para um servidor local.
"""
from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Optional

USER_AGENT = "EasyGameTranslator-components/4 (+https://github.com)"

# Só fontes oficiais. (Cada uma é o host de distribuição do próprio projeto.)
OFFICIAL_HOSTS: frozenset[str] = frozenset({
    "pypi.org", "files.pythonhosted.org",                        # PyPI
    "www.python.org", "python.org",                               # Python
    "github.com", "api.github.com", "objects.githubusercontent.com", "raw.githubusercontent.com",
    "release-assets.githubusercontent.com",                       # arquivos de releases do GitHub
    "huggingface.co",                                             # modelos (quando oficial do projeto)
    "ollama.com", "registry.ollama.ai",                           # Ollama
    "digi.bib.uni-mannheim.de",                                   # instalador do Tesseract (UB Mannheim)
    "argos-net.com",                                              # pacotes de idioma do Argos (índice oficial)
})


class NetworkError(Exception):
    """Falha de rede/HTTP com mensagem amigável em `offline` quando não há internet."""

    def __init__(self, msg: str, offline: bool = False, status: int = 0):
        super().__init__(msg)
        self.offline, self.status = offline, status


class HostNotAllowed(NetworkError):
    pass


class AllowList:
    def __init__(self, hosts: Iterable[str] = OFFICIAL_HOSTS, allow_local: bool = False):
        self.hosts = frozenset(h.lower() for h in hosts)
        self.allow_local = allow_local

    def check(self, url: str) -> str:
        """Valida a URL (https + host oficial; local só se permitido). Devolve a URL."""
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or "").lower()
        if p.username or p.password:
            raise HostNotAllowed("URL com credenciais não é permitida")
        if self.allow_local and host in ("127.0.0.1", "localhost") and p.scheme in ("http", "https"):
            return url
        if p.scheme != "https":
            raise HostNotAllowed("apenas HTTPS é permitido")
        if host not in self.hosts:
            raise HostNotAllowed(f"host não permitido: {host or '?'}")
        return url


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow: AllowList):
        self.allow = allow

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.allow.check(urllib.parse.urljoin(req.full_url, newurl))      # destino também precisa ser oficial
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(allow: AllowList) -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    return urllib.request.build_opener(_SafeRedirect(allow), urllib.request.HTTPSHandler(context=ctx))


def _wrap(exc: Exception) -> NetworkError:
    if isinstance(exc, NetworkError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        return NetworkError(f"HTTP {exc.code}", status=exc.code)
    reason = getattr(exc, "reason", exc)
    offline = isinstance(reason, (socket.gaierror, ConnectionError, TimeoutError, socket.timeout, OSError)) \
        or isinstance(exc, (socket.timeout, TimeoutError))
    return NetworkError("sem internet ou servidor inacessível" if offline else str(exc), offline=offline)


class Http:
    """Cliente mínimo. Substituível nos testes (métodos get_json / head / open_stream)."""

    def __init__(self, allow: Optional[AllowList] = None, timeout: float = 12.0):
        self.allow = allow or AllowList()
        self.timeout = timeout

    def _req(self, url: str, method: str = "GET", headers: Optional[dict] = None) -> urllib.request.Request:
        self.allow.check(url)
        h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        h.update(headers or {})
        return urllib.request.Request(url, method=method, headers=h)

    def get_bytes(self, url: str, limit: int = 8_000_000) -> bytes:
        try:
            with _opener(self.allow).open(self._req(url), timeout=self.timeout) as r:
                return r.read(limit + 1)[:limit]
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc) from exc

    def get_json(self, url: str, limit: int = 8_000_000) -> Any:
        data = self.get_bytes(url, limit)
        try:
            return json.loads(data.decode("utf-8"))
        except ValueError as exc:
            raise NetworkError(f"resposta inválida de {urllib.parse.urlsplit(url).hostname}") from exc

    def get_text(self, url: str, limit: int = 4_000_000) -> str:
        return self.get_bytes(url, limit).decode("utf-8", "replace")

    def head(self, url: str) -> dict:
        """Cabeçalhos (content-length, etc.) com HEAD — segue redirecionamentos oficiais."""
        try:
            with _opener(self.allow).open(self._req(url, "HEAD"), timeout=self.timeout) as r:
                return {k.lower(): v for k, v in r.headers.items()} | {"_status": r.status, "_url": r.geturl()}
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc) from exc

    def content_length(self, url: str) -> Optional[int]:
        try:
            v = self.head(url).get("content-length")
            return int(v) if v is not None else None
        except (NetworkError, ValueError):
            return None

    def open_stream(self, url: str, start: int = 0):
        """Abre o corpo para download em streaming (Range se `start`>0). O chamador fecha."""
        headers = {"Range": f"bytes={start}-"} if start > 0 else {}
        try:
            return _opener(self.allow).open(self._req(url, "GET", headers), timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc) from exc
