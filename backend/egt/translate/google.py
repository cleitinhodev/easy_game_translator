"""Google Tradutor — endpoints públicos da web/extensão (NÃO oficial, sem chave).

1º: clients5.google.com/translate_a/t (client=dict-chrome-ex, POST) — o mesmo da extensão do Chrome.
2º (reserva): translate.googleapis.com/translate_a/single (client=gtx).
O antigo deep-translator usava translate.google.com/m (página para celular), que desde 2026 responde
com 302 → página "sorry"/429; por isso ele foi removido.
"""
from __future__ import annotations

import time

from ..languages import engine_lang
from . import http
from .base import RateLimited, TranslationError, Translator, split_chunks

CLIENTS5 = "https://clients5.google.com/translate_a/t"
GTX = "https://translate.googleapis.com/translate_a/single"
MIN_INTERVAL = 0.8      # segundos entre pedidos (todas as threads)
CHUNK = 2800


def _parse_clients5(data) -> str:
    # ["texto"] | [["texto", "idioma-detectado"]] | "texto"
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        parts = []
        for item in data:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, list) and item and isinstance(item[0], str):
                parts.append(item[0])
        return "".join(parts)
    return ""


def _parse_gtx(data) -> str:
    try:
        return "".join(seg[0] for seg in data[0] if isinstance(seg, list) and seg and isinstance(seg[0], str))
    except (TypeError, IndexError, KeyError):
        return ""


class GoogleTranslate(Translator):
    id = "google"
    name = "Google Translate"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return True, "ok"

    def _clients5(self, chunk: str, s: str, t: str) -> str:
        http.throttle("google", MIN_INTERVAL)
        r = http.request("Google", "POST", CLIENTS5, timeout=self.timeout,
                         params={"client": "dict-chrome-ex", "sl": s, "tl": t}, data={"q": chunk})
        http.check("Google", r, rate_wait=120)
        return _parse_clients5(http.json_of("Google", r)).strip()

    def _gtx(self, chunk: str, s: str, t: str) -> str:
        http.throttle("google", MIN_INTERVAL)
        r = http.request("Google", "POST", GTX, timeout=self.timeout,
                         params={"client": "gtx", "sl": s, "tl": t, "dt": "t"}, data={"q": chunk})
        http.check("Google", r, rate_wait=120)
        return _parse_gtx(http.json_of("Google", r)).strip()

    def translate_chunk(self, chunk: str, s: str, t: str) -> str:
        errors: list[Exception] = []
        for attempt, fn in enumerate((self._clients5, self._clients5, self._gtx)):
            try:
                out = fn(chunk, s, t)
                if out:
                    return out
                errors.append(TranslationError("Google: resposta vazia", "empty"))
            except RateLimited as exc:        # 429/302: não insiste no mesmo endpoint
                errors.append(exc)
                if fn is self._gtx:
                    break
                continue
            except TranslationError as exc:
                if exc.code in ("network", "timeout"):
                    raise
                errors.append(exc)
            if attempt == 0:
                time.sleep(0.4)                # resposta vazia esporádica do clients5: tenta de novo
        rl = [e for e in errors if isinstance(e, RateLimited)]
        if rl and len(rl) == len(errors):
            raise rl[-1]
        raise errors[-1] if errors else TranslationError("Google: resposta vazia", "empty")

    def translate(self, text: str, src: str, tgt: str) -> str:
        s = engine_lang("google", src) if src else "auto"
        t = engine_lang("google", tgt)
        return "\n".join(self.translate_chunk(c, s, t) for c in split_chunks(text, CHUNK))
