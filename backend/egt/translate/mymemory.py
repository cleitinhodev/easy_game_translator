"""MyMemory (API REST gratuita; ~5000 caracteres/dia sem e-mail)."""
from __future__ import annotations

from ..languages import engine_lang
from .base import RateLimited, TranslationError, Translator, split_chunks

URL = "https://api.mymemory.translated.net/get"


class MyMemoryTranslate(Translator):
    id = "mymemory"
    name = "MyMemory"

    def __init__(self, timeout: float = 8.0, email: str = ""):
        self.timeout = timeout
        self.email = email

    def available(self) -> tuple[bool, str]:
        try:
            import requests  # noqa: F401
            return True, "ok"
        except ImportError:
            return False, "pip install requests"

    def translate(self, text: str, src: str, tgt: str) -> str:
        import requests
        s = engine_lang("mymemory", src) if src else "Autodetect"
        t = engine_lang("mymemory", tgt)
        out = []
        for chunk in split_chunks(text, 450):
            params = {"q": chunk, "langpair": f"{s}|{t}"}
            if self.email:
                params["de"] = self.email
            try:
                r = requests.get(URL, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                raise TranslationError(f"MyMemory: {type(exc).__name__}") from exc
            if r.status_code == 429:
                raise RateLimited("MyMemory: cota excedida", retry_after=300)
            try:
                data = r.json()
            except ValueError as exc:
                raise TranslationError("MyMemory: resposta inválida") from exc
            status = int(data.get("responseStatus", r.status_code) or 0)
            if status == 429 or "QUOTA" in str(data.get("responseDetails", "")).upper():
                raise RateLimited("MyMemory: cota diária excedida", retry_after=3600)
            if status != 200:
                raise TranslationError(f"MyMemory: {data.get('responseDetails', status)}")
            res = (data.get("responseData") or {}).get("translatedText") or ""
            if "MYMEMORY WARNING" in res.upper():
                raise RateLimited("MyMemory: aviso de cota", retry_after=3600)
            out.append(res)
        return "\n".join(out)
