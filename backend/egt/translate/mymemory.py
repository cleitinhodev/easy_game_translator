"""MyMemory (Translated) — API REST oficial e gratuita, sem chave.

Cota: ~5.000 caracteres/dia por IP; informando um e-mail (parâmetro `de`), ~50.000/dia.
A memória de tradução é colaborativa e às vezes tem entradas ruins ("Hello world translated ...");
por isso preferimos a tradução automática (MT) e descartamos entradas humanas suspeitas.
"""
from __future__ import annotations

import re

from ..change import normalize_text
from ..languages import engine_lang
from . import http
from .base import RateLimited, TranslationError, Translator, split_chunks

URL = "https://api.mymemory.translated.net/get"
MIN_INTERVAL = 0.5
CHUNK = 450
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", " ", normalize_text(s or "")).strip().lower()


def pick_match(query: str, data: dict) -> str:
    """Escolhe a melhor tradução: MT > entrada humana idêntica (sem ecoar a origem) > translatedText."""
    q = _norm(query)
    matches = [m for m in (data.get("matches") or []) if isinstance(m, dict) and (m.get("translation") or "").strip()]

    def bad(tr: str) -> bool:
        n = _norm(tr)
        return not n or (len(q) >= 4 and (n == q or (q in n and len(n) > len(q) + 3)))
    mt = [m for m in matches if str(m.get("created-by", "")).upper().startswith("MT")]
    for m in mt:
        if not bad(m["translation"]):
            return m["translation"]
    human = [m for m in matches if _norm(m.get("segment", "")) == q and not bad(m["translation"])]
    if human:
        human.sort(key=lambda m: (float(m.get("match") or 0), int(m.get("usage-count") or 0),
                                  int(str(m.get("quality") or 0) or 0)), reverse=True)
        return human[0]["translation"]
    best = ((data.get("responseData") or {}).get("translatedText") or "").strip()
    if best and not bad(best):
        return best
    return ""


class MyMemoryTranslate(Translator):
    id = "mymemory"
    name = "MyMemory"

    def __init__(self, timeout: float = 8.0, email: str = ""):
        self.timeout = timeout
        self.email = email.strip() if email and _EMAIL.match(email.strip()) else ""

    def available(self) -> tuple[bool, str]:
        return True, "ok"

    def translate(self, text: str, src: str, tgt: str) -> str:
        s = engine_lang("mymemory", src) if src else "Autodetect"
        if s == "auto":
            s = "Autodetect"
        t = engine_lang("mymemory", tgt)
        out = []
        for chunk in split_chunks(text, CHUNK):
            params = {"q": chunk, "langpair": f"{s}|{t}", "mt": "1"}
            if self.email:
                params["de"] = self.email
            http.throttle("mymemory", MIN_INTERVAL)
            r = http.request("MyMemory", "GET", URL, params=params, timeout=self.timeout)
            if r.status_code == 429:
                raise RateLimited("MyMemory: cota excedida", retry_after=300, code="quota")
            http.check("MyMemory", r)
            data = http.json_of("MyMemory", r)
            if not isinstance(data, dict):
                raise TranslationError("MyMemory: resposta inválida", "bad_response")
            details = str(data.get("responseDetails", ""))
            status = int(data.get("responseStatus", 200) or 0)
            text_out = str((data.get("responseData") or {}).get("translatedText") or "")
            if data.get("quotaFinished") or status == 429 or "QUOTA" in details.upper() \
                    or "MYMEMORY WARNING" in text_out.upper():
                raise RateLimited("MyMemory: cota diária esgotada", retry_after=3600, code="quota")
            if status == 403 and "INVALID" in details.upper() and "LANGUAGE" in details.upper():
                raise TranslationError("MyMemory: idioma não suportado", "unsupported_lang")
            if status != 200:
                raise TranslationError(f"MyMemory: erro {status}", "http")
            res = pick_match(chunk, data)
            if not res:
                raise TranslationError("MyMemory: só havia traduções de baixa qualidade", "low_quality")
            out.append(res)
        return "\n".join(out)
