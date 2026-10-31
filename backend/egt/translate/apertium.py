"""Apertium — tradutor livre (regras), API pública gratuita de apertium.org, sem chave.

Só alguns pares (ex.: inglês↔espanhol, espanhol↔português, francês→espanhol, hindi↔urdu); quando não
existe o par direto, tenta passar pelo espanhol (ex.: inglês→espanhol→português). O endereço pode
apontar para um servidor próprio (APy).
"""
from __future__ import annotations

import threading
import time

from ..languages import engine_lang
from . import http
from .base import TranslationError, Translator, split_chunks

DEFAULT_URL = "https://apertium.org/apy"
MIN_INTERVAL = 0.5
CHUNK = 2000
PAIRS_TTL = 6 * 3600

_lock = threading.Lock()
_pairs: dict[str, tuple[float, set]] = {}


def _variants(code: str) -> list[str]:
    return {"por": ["por_BR", "por"], "eng": ["eng", "eng_US"], "cat": ["cat"]}.get(code, [code])


class ApertiumTranslate(Translator):
    id = "apertium"
    name = "Apertium"

    def __init__(self, url: str = DEFAULT_URL, timeout: float = 8.0):
        self.raw = (url or "").strip() or DEFAULT_URL
        self.url = http.clean_url(self.raw)
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self.url else (False, "endereço do servidor inválido")

    def pairs(self) -> set:
        with _lock:
            hit = _pairs.get(self.url)
            if hit and hit[0] > time.monotonic():
                return hit[1]
        http.throttle("apertium", MIN_INTERVAL)
        r = http.request("Apertium", "GET", f"{self.url}/listPairs", timeout=self.timeout)
        http.check("Apertium", r)
        data = http.json_of("Apertium", r)
        got = {(p.get("sourceLanguage", ""), p.get("targetLanguage", "")) for p in (data.get("responseData") or [])
               if isinstance(p, dict)}
        if not got:
            raise TranslationError("Apertium: lista de pares vazia", "bad_response")
        with _lock:
            _pairs[self.url] = (time.monotonic() + PAIRS_TTL, got)
        return got

    def route(self, s: str, t: str) -> list[tuple[str, str]]:
        """Pares a usar (direto ou via espanhol). Lista vazia = não suportado."""
        pairs = self.pairs()

        def find(a: str, b: str):
            for x in _variants(a):
                for y in _variants(b):
                    if (x, y) in pairs:
                        return (x, y)
            return None
        direct = find(s, t)
        if direct:
            return [direct]
        if "spa" not in (s, t):
            a, b = find(s, "spa"), find("spa", t)
            if a and b:
                return [a, b]
        return []

    def _call(self, chunk: str, pair: tuple[str, str]) -> str:
        http.throttle("apertium", MIN_INTERVAL)
        r = http.request("Apertium", "POST", f"{self.url}/translate", timeout=self.timeout,
                         data={"langpair": f"{pair[0]}|{pair[1]}", "q": chunk, "markUnknown": "no"})
        if r.status_code == 400:
            raise TranslationError("Apertium: par de idiomas não instalado", "unsupported_lang")
        http.check("Apertium", r)
        data = http.json_of("Apertium", r)
        out = ((data.get("responseData") or {}).get("translatedText") or "") if isinstance(data, dict) else ""
        if not out.strip():
            raise TranslationError("Apertium: resposta vazia", "empty")
        return out

    def translate(self, text: str, src: str, tgt: str) -> str:
        if not src or src == "auto":
            raise TranslationError("Apertium precisa do idioma de origem (não detecta sozinho)", "unsupported_lang")
        s, t = engine_lang("apertium", src), engine_lang("apertium", tgt)
        route = self.route(s, t)
        if not route:
            raise TranslationError(f"Apertium: sem o par {src}→{tgt}", "unsupported_lang")
        out = []
        for chunk in split_chunks(text, CHUNK):
            for pair in route:
                chunk = self._call(chunk, pair)
            out.append(chunk)
        return "\n".join(out)
