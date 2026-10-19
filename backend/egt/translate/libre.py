"""LibreTranslate (URL e chave configuráveis) e Lingva (instância pública, sem chave)."""
from __future__ import annotations

from urllib.parse import quote

from ..languages import engine_lang
from .base import RateLimited, TranslationError, Translator, split_chunks


class LibreTranslate(Translator):
    id = "libre"
    name = "LibreTranslate"

    def __init__(self, url: str = "http://localhost:5000", api_key: str = "", timeout: float = 8.0):
        self.url = (url or "").rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self.url else (False, "configure a URL do servidor")

    def translate(self, text: str, src: str, tgt: str) -> str:
        import requests
        payload = {"q": text, "source": engine_lang("libre", src) if src else "auto",
                   "target": engine_lang("libre", tgt), "format": "text"}
        if self.api_key:
            payload["api_key"] = self.api_key
        try:
            r = requests.post(f"{self.url}/translate", json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TranslationError(f"LibreTranslate: {type(exc).__name__}") from exc
        if r.status_code == 429:
            raise RateLimited("LibreTranslate: limite", retry_after=60)
        if r.status_code != 200:
            try:
                msg = r.json().get("error", r.status_code)
            except ValueError:
                msg = r.status_code
            raise TranslationError(f"LibreTranslate: {msg}")
        try:
            return r.json()["translatedText"]
        except (ValueError, KeyError) as exc:
            raise TranslationError("LibreTranslate: resposta inválida") from exc


class LingvaTranslate(Translator):
    id = "lingva"
    name = "Lingva (Google sem rastreio)"

    def __init__(self, url: str = "https://lingva.ml", timeout: float = 8.0):
        self.url = (url or "").rstrip("/")
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self.url else (False, "configure a URL da instância")

    def translate(self, text: str, src: str, tgt: str) -> str:
        import requests
        s = engine_lang("lingva", src) if src else "auto"
        t = engine_lang("lingva", tgt)
        out = []
        for chunk in split_chunks(text, 900):
            try:
                r = requests.get(f"{self.url}/api/v1/{s}/{t}/{quote(chunk, safe='')}", timeout=self.timeout)
            except requests.RequestException as exc:
                raise TranslationError(f"Lingva: {type(exc).__name__}") from exc
            if r.status_code == 429:
                raise RateLimited("Lingva: limite", retry_after=60)
            if r.status_code != 200:
                raise TranslationError(f"Lingva: HTTP {r.status_code}")
            try:
                out.append(r.json()["translation"])
            except (ValueError, KeyError) as exc:
                raise TranslationError("Lingva: resposta inválida") from exc
        return "\n".join(out)
