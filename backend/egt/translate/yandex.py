"""Yandex Tradutor — endpoint do app Android (NÃO oficial, sem chave). Pode parar de funcionar."""
from __future__ import annotations

import uuid

from ..languages import engine_lang
from . import http
from .base import RateLimited, TranslationError, Translator, split_chunks

API = "https://translate.yandex.net/api/v1/tr.json/translate"
MIN_INTERVAL = 0.8
CHUNK = 4000
_UCID = uuid.uuid4().hex   # identificador aleatório por execução (não identifica o usuário)


class YandexTranslate(Translator):
    id = "yandex"
    name = "Yandex Translate"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return True, "ok"

    def translate(self, text: str, src: str, tgt: str) -> str:
        t = engine_lang("yandex", tgt)
        s = engine_lang("yandex", src) if src else ""
        lang = f"{s}-{t}" if s and s != "auto" else t
        out = []
        for chunk in split_chunks(text, CHUNK):
            http.throttle("yandex", MIN_INTERVAL)
            r = http.request("Yandex", "POST", API, timeout=self.timeout,
                             params={"srv": "android", "id": f"{_UCID}-0-0", "lang": lang}, data={"text": chunk})
            data = None
            if r.status_code in (400, 403, 413, 422):
                try:
                    data = r.json()
                except ValueError:
                    data = None
            if data is None:
                http.check("Yandex", r)
                data = http.json_of("Yandex", r)
            code = int(data.get("code", 0) or 0) if isinstance(data, dict) else 0
            if code == 501:
                raise TranslationError("Yandex: direção de tradução não suportada", "unsupported_lang")
            if code in (402, 403, 404, 405, 429):
                raise RateLimited(f"Yandex: bloqueado/limite (código {code})", retry_after=300)
            if code != 200:
                raise TranslationError(f"Yandex: erro (código {code})", "http")
            out.append("\n".join(data.get("text") or []))
        return "\n".join(out)
