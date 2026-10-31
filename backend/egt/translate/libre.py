"""LibreTranslate — software livre. Use um servidor próprio (grátis; ex.: Docker no seu PC) ou o
libretranslate.com com chave paga. Não há mais instâncias públicas gratuitas confiáveis em 2026.

(O Lingva, que ficava aqui, foi removido na 4.0.8: todas as instâncias públicas pararam ou devolvem o
texto sem traduzir. O Mozhi o substitui.)
"""
from __future__ import annotations

from ..languages import engine_lang
from . import http
from .base import TranslationError, Translator, split_chunks

OFFICIAL = "https://libretranslate.com"
CHUNK = 4000


class LibreTranslate(Translator):
    id = "libre"
    name = "LibreTranslate"

    def __init__(self, url: str = "", api_key: str = "", timeout: float = 8.0):
        self.raw = (url or "").strip()
        self.url = http.clean_url(self.raw)
        self.api_key = api_key or ""
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        if not self.raw:
            return False, "informe o endereço do servidor (o seu ou https://libretranslate.com com chave)"
        if not self.url:
            return False, "endereço do servidor inválido"
        if self.url.rstrip("/") == OFFICIAL and not self.api_key:
            return False, "o libretranslate.com exige chave de API"
        return True, "ok"

    def unavailable_code(self, why: str = "") -> str:
        """Sem endereço/endereço inválido → config; libretranslate.com sem chave → no_key."""
        return "no_key" if self.url and self.url.rstrip("/") == OFFICIAL and not self.api_key else "config"

    def _error(self, r) -> TranslationError:
        try:
            msg = str(r.json().get("error", ""))
        except (ValueError, AttributeError):
            msg = ""
        low = msg.lower()
        if "api key" in low or "api_key" in low:
            if "invalid" in low:
                return TranslationError("LibreTranslate: chave inválida", "bad_key")
            return TranslationError("LibreTranslate: este servidor exige chave de API", "no_key")
        if "not supported" in low or "language" in low:
            return TranslationError("LibreTranslate: idioma não suportado neste servidor", "unsupported_lang")
        return TranslationError(f"LibreTranslate: erro HTTP {r.status_code}", "http")

    def languages(self) -> list:
        """GET /languages — confirma que o servidor responde (não gasta cota)."""
        ok, why = self.available()
        if not ok:
            raise TranslationError(f"LibreTranslate: {why}", self.unavailable_code())
        r = http.request("LibreTranslate", "GET", f"{self.url}/languages", timeout=self.timeout)
        http.check("LibreTranslate", r)
        data = http.json_of("LibreTranslate", r)
        if not isinstance(data, list):
            raise TranslationError("LibreTranslate: resposta inválida", "bad_response")
        return data

    def translate(self, text: str, src: str, tgt: str) -> str:
        ok, why = self.available()
        if not ok:
            raise TranslationError(f"LibreTranslate: {why}", self.unavailable_code())
        out = []
        for chunk in split_chunks(text, CHUNK):
            payload = {"q": chunk, "source": engine_lang("libre", src) if src else "auto",
                       "target": engine_lang("libre", tgt), "format": "text"}
            if self.api_key:
                payload["api_key"] = self.api_key
            http.throttle("libre:" + self.url, 0.2)
            r = http.request("LibreTranslate", "POST", f"{self.url}/translate", json=payload, timeout=self.timeout)
            if r.status_code in (400, 403) :
                raise self._error(r)
            http.check("LibreTranslate", r)
            data = http.json_of("LibreTranslate", r)
            res = data.get("translatedText", "") if isinstance(data, dict) else ""
            if not res:
                raise TranslationError("LibreTranslate: resposta vazia", "empty")
            out.append(res)
        return "\n".join(out)
