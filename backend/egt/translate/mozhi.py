"""Mozhi — front-end livre e sem rastreio (codeberg.org/aryak/mozhi) que repassa o texto para um motor
(DuckDuckGo/Bing, Yandex, Google...). Substitui o Lingva, cujas instâncias públicas pararam em 2026.

Sem chave. As instâncias são mantidas por voluntários: tenta a escolhida e, no modo automático,
alterna entre as conhecidas até uma responder.
"""
from __future__ import annotations

import threading

from ..languages import engine_lang
from . import http
from .base import RateLimited, TranslationError, Translator, split_chunks

INSTANCES = ("https://mozhi.aryak.me", "https://translate.projectsegfau.lt", "https://mozhi.ducks.party",
             "https://mozhi.adminforge.de", "https://mozhi.pussthecat.org", "https://mzh.dc09.xyz")
ENGINES = ("duckduckgo", "yandex", "google")
MIN_INTERVAL = 0.8
CHUNK = 1500

_lock = threading.Lock()
_good: dict[str, str] = {}    # motor → última instância que respondeu


class MozhiTranslate(Translator):
    id = "mozhi"
    name = "Mozhi"

    def __init__(self, url: str = "", engine: str = "duckduckgo", timeout: float = 8.0):
        self.custom = (url or "").strip()
        self.url = http.clean_url(self.custom) if self.custom else None
        self.engine = engine if engine in ENGINES else "duckduckgo"
        self.timeout = timeout
        self.last_instance = ""

    def available(self) -> tuple[bool, str]:
        if self.custom and not self.url:
            return False, "endereço da instância inválido"
        return True, "ok"

    def _instances(self) -> list[str]:
        if self.url:
            return [self.url]
        with _lock:
            first = _good.get(self.engine)
        rest = [u for u in INSTANCES if u != first]
        return ([first] if first else []) + rest

    def _one(self, base: str, chunk: str, s: str, t: str) -> str:
        http.throttle("mozhi:" + base, MIN_INTERVAL)
        r = http.request("Mozhi", "GET", f"{base}/api/translate", timeout=self.timeout,
                         params={"engine": self.engine, "from": s, "to": t, "text": chunk})
        if r.status_code == 200 and "json" not in r.headers.get("Content-Type", "json"):
            low = r.text.lower()
            if "language code invalid" in low:
                raise TranslationError("Mozhi: idioma não suportado por este motor", "unsupported_lang")
            raise TranslationError("Mozhi: resposta inválida", "bad_response")
        if r.status_code == 500 and "429" in r.text:
            raise RateLimited("Mozhi: o motor escolhido bloqueou a instância (429)", retry_after=300)
        if r.status_code in (400, 500) and "language code invalid" in r.text.lower():
            raise TranslationError("Mozhi: idioma não suportado por este motor", "unsupported_lang")
        http.check("Mozhi", r, rate_wait=120)
        data = http.json_of("Mozhi", r)
        out = (data.get("translated-text") if isinstance(data, dict) else "") or ""
        if not out.strip():
            raise TranslationError("Mozhi: resposta vazia", "empty")
        return out

    def translate(self, text: str, src: str, tgt: str) -> str:
        key = "mozhi" if self.engine == "duckduckgo" else f"mozhi:{self.engine}"
        s = engine_lang(key, src) if src else "auto"
        t = engine_lang(key, tgt)
        last: Exception = TranslationError("Mozhi: nenhuma instância respondeu", "network")
        for base in self._instances():
            try:
                out = "\n".join(self._one(base, c, s, t) for c in split_chunks(text, CHUNK))
            except TranslationError as exc:
                if exc.code == "unsupported_lang":
                    raise
                last = exc
                continue
            with _lock:
                _good[self.engine] = base
            self.last_instance = base
            return out
        raise last
