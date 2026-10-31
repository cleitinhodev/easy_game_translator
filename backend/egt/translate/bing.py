"""Microsoft Bing Tradutor — endpoint da página bing.com/translator (NÃO oficial, sem chave).

Abre a página uma vez para ler os parâmetros de sessão (IG, IID, key, token; o token vale ~1 h) e
depois usa POST /ttranslatev3. Limite de ~1000 caracteres por pedido (o texto é dividido).
"""
from __future__ import annotations

import re
import threading
import time

from ..languages import engine_lang
from . import http
from .base import RateLimited, TranslationError, Translator, split_chunks

PAGE = "https://www.bing.com/translator"
API = "https://www.bing.com/ttranslatev3"
MIN_INTERVAL = 0.6
CHUNK = 1000

_IG = re.compile(r'IG:"([A-Za-z0-9]+)"')
_IID = re.compile(r'data-iid="(translator\.\d+)"')
_HELPER = re.compile(r'params_AbusePreventionHelper\s*=\s*\[\s*(\d+)\s*,\s*"([^"]+)"\s*,\s*(\d+)')

_lock = threading.Lock()
_sess: dict = {}          # sessão compartilhada (por processo): ig, iid, key, token, until, n


def _load_session(timeout: float) -> dict:
    http.throttle("bing", MIN_INTERVAL)
    r = http.request("Bing", "GET", PAGE, timeout=timeout, allow_redirects=True)
    http.check("Bing", r)
    html = r.text
    ig, iid, helper = _IG.search(html), _IID.search(html), _HELPER.search(html)
    if not (ig and iid and helper):
        raise TranslationError("Bing: a página do tradutor mudou (sem token)", "bad_response")
    ttl = min(int(helper.group(3)) / 1000.0, 3600.0)
    return {"ig": ig.group(1), "iid": iid.group(1), "key": helper.group(1), "token": helper.group(2),
            "until": time.monotonic() + max(60.0, ttl - 120.0), "n": 1}


def reset_session() -> None:
    with _lock:
        _sess.clear()


class BingTranslate(Translator):
    id = "bing"
    name = "Bing Translator"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return True, "ok"

    def _session(self, fresh: bool = False) -> dict:
        with _lock:
            if fresh or not _sess or _sess.get("until", 0) < time.monotonic():
                _sess.clear()
                _sess.update(_load_session(self.timeout))
            _sess["n"] += 1
            return dict(_sess)

    def _one(self, chunk: str, s: str, t: str, fresh: bool = False) -> str:
        ss = self._session(fresh)
        http.throttle("bing", MIN_INTERVAL)
        r = http.request("Bing", "POST", API, timeout=self.timeout,
                         params={"isVertical": "1", "IG": ss["ig"], "IID": f"{ss['iid']}.{ss['n']}"},
                         data={"fromLang": s, "to": t, "text": chunk, "token": ss["token"], "key": ss["key"],
                               "tryFetchingGenderDebiasedTranslations": "true"},
                         headers={"Referer": PAGE, "Origin": "https://www.bing.com"})
        http.check("Bing", r, rate_wait=120)
        data = http.json_of("Bing", r) if r.text.strip() else None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            tr = (data[0].get("translations") or [{}])[0].get("text", "")
            if tr:
                return tr
            raise TranslationError("Bing: resposta vazia", "empty")
        status = data.get("statusCode") if isinstance(data, dict) else None
        if status == 429:
            raise RateLimited("Bing: muitas requisições", retry_after=120)
        if status == 400 and not fresh:
            return None  # token expirado/sessão inválida → nova sessão
        if status == 400:
            raise TranslationError("Bing: idioma não suportado ou pedido recusado", "unsupported_lang")
        raise TranslationError("Bing: resposta inesperada", "bad_response")

    def translate(self, text: str, src: str, tgt: str) -> str:
        s = engine_lang("bing", src) if src else "auto-detect"
        if s == "auto":
            s = "auto-detect"
        t = engine_lang("bing", tgt)
        out = []
        for chunk in split_chunks(text, CHUNK):
            res = self._one(chunk, s, t)
            if res is None:
                res = self._one(chunk, s, t, fresh=True)
            out.append(res)
        return "\n".join(out)
