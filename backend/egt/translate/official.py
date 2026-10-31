"""APIs oficiais que pedem chave do usuário (todas com nível/crédito gratuito — veja o README).

A chave é lida das configurações CIFRADAS (vault.py) só na hora do pedido e vai apenas em cabeçalhos
ou no corpo do POST (nunca na URL, para não aparecer em logs de proxy). Nenhuma mensagem de erro
inclui o corpo da resposta (alguns serviços ecoam a chave ou o texto).
"""
from __future__ import annotations

import hashlib
import secrets
import time

from ..languages import engine_lang
from . import http
from .base import RateLimited, TranslationError, Translator, split_chunks


def _need(*vals: str) -> bool:
    return all((v or "").strip() for v in vals)


# --------------------------------------------------------------------------- DeepL
class DeepLTranslate(Translator):
    """DeepL API (Free: chaves terminadas em ':fx' → api-free.deepl.com; Pro → api.deepl.com)."""
    id = "deepl"
    name = "DeepL"

    def __init__(self, api_key: str = "", timeout: float = 8.0):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    @property
    def base(self) -> str:
        return "https://api-free.deepl.com" if self.api_key.endswith(":fx") else "https://api.deepl.com"

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self.api_key else (False, "informe a chave da API do DeepL")

    def translate(self, text: str, src: str, tgt: str) -> str:
        if not self.api_key:
            raise TranslationError("DeepL: sem chave", "no_key")
        body = {"text": split_chunks(text, 4500), "target_lang": engine_lang("deepl", tgt)}
        if src and src != "auto":
            body["source_lang"] = engine_lang("deepl", src, source=True)
        http.throttle("deepl", 0.2)
        r = http.request("DeepL", "POST", f"{self.base}/v2/translate", timeout=self.timeout, json=body,
                         headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"})
        if r.status_code == 400:
            raise TranslationError("DeepL: idioma não suportado ou pedido inválido", "unsupported_lang")
        http.check("DeepL", r)
        data = http.json_of("DeepL", r)
        out = [t.get("text", "") for t in (data.get("translations") or []) if isinstance(t, dict)]
        return "\n".join(out)


# --------------------------------------------------------------------------- Azure
class MicrosoftTranslate(Translator):
    """Azure AI Translator (REST v3). Nível F0 gratuito: 2 milhões de caracteres/mês."""
    id = "microsoft"
    name = "Microsoft Azure Translator"
    API = "https://api.cognitive.microsofttranslator.com/translate"

    def __init__(self, api_key: str = "", region: str = "", timeout: float = 8.0):
        self.api_key = (api_key or "").strip()
        self.region = (region or "").strip()
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self.api_key else (False, "informe a chave do Azure Translator")

    def translate(self, text: str, src: str, tgt: str) -> str:
        if not self.api_key:
            raise TranslationError("Azure: sem chave", "no_key")
        params = {"api-version": "3.0", "to": engine_lang("microsoft", tgt)}
        if src and src != "auto":
            params["from"] = engine_lang("microsoft", src)
        headers = {"Ocp-Apim-Subscription-Key": self.api_key, "Content-Type": "application/json"}
        if self.region and self.region.lower() != "global":
            headers["Ocp-Apim-Subscription-Region"] = self.region
        out = []
        for chunk in split_chunks(text, 10000):
            http.throttle("microsoft", 0.2)
            r = http.request("Azure", "POST", self.API, timeout=self.timeout, params=params, headers=headers,
                             json=[{"Text": chunk}])
            if r.status_code == 400:
                raise TranslationError("Azure: idioma não suportado ou pedido inválido", "unsupported_lang")
            if r.status_code == 403:
                raise RateLimited("Azure: cota gratuita do mês esgotada", retry_after=3600, code="quota")
            http.check("Azure", r)
            data = http.json_of("Azure", r)
            try:
                out.append(data[0]["translations"][0]["text"])
            except (TypeError, IndexError, KeyError) as exc:
                raise TranslationError("Azure: resposta inválida", "bad_response") from exc
        return "\n".join(out)


# --------------------------------------------------------------------------- Google Cloud
class GoogleCloudTranslate(Translator):
    """Google Cloud Translation API (Basic v2) com chave de API. 500 mil caracteres/mês de crédito."""
    id = "gcloud"
    name = "Google Cloud Translation"
    API = "https://translation.googleapis.com/language/translate/v2"

    def __init__(self, api_key: str = "", timeout: float = 8.0):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self.api_key else (False, "informe a chave do Google Cloud")

    def translate(self, text: str, src: str, tgt: str) -> str:
        if not self.api_key:
            raise TranslationError("Google Cloud: sem chave", "no_key")
        body = {"q": split_chunks(text, 4500), "target": engine_lang("gcloud", tgt), "format": "text"}
        if src and src != "auto":
            body["source"] = engine_lang("gcloud", src)
        http.throttle("gcloud", 0.2)
        r = http.request("Google Cloud", "POST", self.API, timeout=self.timeout, json=body,
                         headers={"X-Goog-Api-Key": self.api_key})
        if r.status_code == 400:
            try:
                reason = str(r.json().get("error", {}).get("message", "")).lower()
            except (ValueError, AttributeError):
                reason = ""
            if "api key" in reason:
                raise TranslationError("Google Cloud: chave inválida", "bad_key")
            raise TranslationError("Google Cloud: idioma não suportado ou pedido inválido", "unsupported_lang")
        if r.status_code == 403:
            raise TranslationError("Google Cloud: API não ativada, sem faturamento ou chave restrita", "bad_key")
        http.check("Google Cloud", r)
        data = http.json_of("Google Cloud", r)
        tr = ((data.get("data") or {}).get("translations") or []) if isinstance(data, dict) else []
        return "\n".join(t.get("translatedText", "") for t in tr if isinstance(t, dict))


# --------------------------------------------------------------------------- Baidu
BAIDU_ERRORS = {
    "52001": ("timeout", "tempo esgotado"), "52002": ("server", "erro do sistema"),
    "52003": ("bad_key", "APP ID inválido"), "54001": ("bad_key", "assinatura inválida (confira a chave secreta)"),
    "54003": ("rate_limit", "muitas requisições"), "54004": ("quota", "saldo/cota esgotado"),
    "54005": ("rate_limit", "textos longos em sequência"), "58000": ("bad_key", "IP não autorizado na conta"),
    "58001": ("unsupported_lang", "idioma não suportado"), "58002": ("bad_key", "serviço desativado na conta"),
    "90107": ("bad_key", "conta não verificada"),
}


class BaiduTranslate(Translator):
    """百度翻译开放平台 (Baidu Fanyi). Edição padrão grátis: 50 mil caracteres/mês (1 pedido/s)."""
    id = "baidu"
    name = "Baidu Fanyi"
    API = "https://fanyi-api.baidu.com/api/trans/vip/translate"

    def __init__(self, appid: str = "", secret: str = "", timeout: float = 8.0):
        self.appid = (appid or "").strip()
        self.secret = (secret or "").strip()
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if _need(self.appid, self.secret) else (False, "informe o APP ID e a chave secreta do Baidu")

    @staticmethod
    def sign(appid: str, q: str, salt: str, secret: str) -> str:
        return hashlib.md5(f"{appid}{q}{salt}{secret}".encode()).hexdigest()

    def translate(self, text: str, src: str, tgt: str) -> str:
        if not _need(self.appid, self.secret):
            raise TranslationError("Baidu: sem chave", "no_key")
        s = engine_lang("baidu", src) if src else "auto"
        t = engine_lang("baidu", tgt)
        out = []
        for chunk in split_chunks(text, 1800):
            salt = str(secrets.randbelow(10**9))
            http.throttle("baidu", 1.05)           # nível padrão: 1 pedido/s
            r = http.request("Baidu", "POST", self.API, timeout=self.timeout,
                             data={"q": chunk, "from": s, "to": t, "appid": self.appid, "salt": salt,
                                   "sign": self.sign(self.appid, chunk, salt, self.secret)})
            http.check("Baidu", r)
            data = http.json_of("Baidu", r)
            err = str(data.get("error_code", "")) if isinstance(data, dict) else ""
            if err and err != "52000":
                code, msg = BAIDU_ERRORS.get(err, ("http", f"erro {err}"))
                if code in ("rate_limit", "quota"):
                    raise RateLimited(f"Baidu: {msg}", retry_after=3600 if code == "quota" else 5, code=code)
                raise TranslationError(f"Baidu: {msg}", code)
            res = [x.get("dst", "") for x in (data.get("trans_result") or []) if isinstance(x, dict)]
            out.append("\n".join(res))
        return "\n".join(out)


# --------------------------------------------------------------------------- Youdao
YOUDAO_ERRORS = {
    "101": ("http", "parâmetro faltando"), "102": ("unsupported_lang", "idioma não suportado"),
    "103": ("http", "texto longo demais"), "108": ("bad_key", "App Key inválida"),
    "110": ("bad_key", "o aplicativo não tem o serviço de tradução de texto"),
    "111": ("bad_key", "conta de desenvolvedor inválida"), "202": ("bad_key", "assinatura inválida (confira o App Secret)"),
    "206": ("bad_key", "horário do PC fora de sincronia"), "401": ("quota", "conta sem saldo"),
    "411": ("rate_limit", "muitas requisições"), "412": ("rate_limit", "textos longos em sequência"),
}


class YoudaoTranslate(Translator):
    """有道智云 (Youdao AI Cloud) — tradução de texto. Novas contas ganham crédito de teste."""
    id = "youdao"
    name = "Youdao"
    API = "https://openapi.youdao.com/api"

    def __init__(self, app_key: str = "", secret: str = "", timeout: float = 8.0):
        self.app_key = (app_key or "").strip()
        self.secret = (secret or "").strip()
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if _need(self.app_key, self.secret) else (False, "informe a App Key e o App Secret do Youdao")

    @staticmethod
    def sign(app_key: str, q: str, salt: str, curtime: str, secret: str) -> str:
        inp = q if len(q) <= 20 else f"{q[:10]}{len(q)}{q[-10:]}"
        return hashlib.sha256(f"{app_key}{inp}{salt}{curtime}{secret}".encode()).hexdigest()

    def translate(self, text: str, src: str, tgt: str) -> str:
        if not _need(self.app_key, self.secret):
            raise TranslationError("Youdao: sem chave", "no_key")
        s = engine_lang("youdao", src) if src else "auto"
        t = engine_lang("youdao", tgt)
        out = []
        for chunk in split_chunks(text, 4500):
            salt, cur = secrets.token_hex(8), str(int(time.time()))
            http.throttle("youdao", 0.3)
            r = http.request("Youdao", "POST", self.API, timeout=self.timeout,
                             data={"q": chunk, "from": s, "to": t, "appKey": self.app_key, "salt": salt,
                                   "sign": self.sign(self.app_key, chunk, salt, cur, self.secret),
                                   "signType": "v3", "curtime": cur})
            http.check("Youdao", r)
            data = http.json_of("Youdao", r)
            err = str(data.get("errorCode", "")) if isinstance(data, dict) else "bad"
            if err != "0":
                code, msg = YOUDAO_ERRORS.get(err, ("http", f"erro {err}"))
                if code in ("rate_limit", "quota"):
                    raise RateLimited(f"Youdao: {msg}", retry_after=3600 if code == "quota" else 10, code=code)
                raise TranslationError(f"Youdao: {msg}", code)
            out.append("\n".join(data.get("translation") or []))
        return "\n".join(out)


# --------------------------------------------------------------------------- NiuTrans
NIU_ERRORS = {
    "13001": ("bad_key", "chave inválida ou sem saldo"), "13002": ("no_key", "chave vazia"),
    "13003": ("http", "conteúdo filtrado"), "10001": ("rate_limit", "muitas requisições"),
    "10003": ("http", "texto longo demais"), "10005": ("unsupported_lang", "idioma de origem não suportado"),
    "10006": ("unsupported_lang", "idioma de destino não suportado"),
    "10007": ("unsupported_lang", "par de idiomas não suportado"),
}


class NiuTransTranslate(Translator):
    """小牛翻译 NiuTrans — API de texto. Plano gratuito: 200 mil caracteres/dia."""
    id = "niutrans"
    name = "NiuTrans"
    API = "https://api.niutrans.com/NiuTransServer/translation"

    def __init__(self, api_key: str = "", timeout: float = 8.0):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self.api_key else (False, "informe a chave do NiuTrans")

    def translate(self, text: str, src: str, tgt: str) -> str:
        if not self.api_key:
            raise TranslationError("NiuTrans: sem chave", "no_key")
        s = engine_lang("niutrans", src) if src else "auto"
        t = engine_lang("niutrans", tgt)
        out = []
        for chunk in split_chunks(text, 4500):
            http.throttle("niutrans", 0.3)
            r = http.request("NiuTrans", "POST", self.API, timeout=self.timeout,
                             data={"from": s, "to": t, "apikey": self.api_key, "src_text": chunk})
            http.check("NiuTrans", r)
            data = http.json_of("NiuTrans", r)
            if not isinstance(data, dict):
                raise TranslationError("NiuTrans: resposta inválida", "bad_response")
            err = str(data.get("error_code", "") or "")
            if err:
                code, msg = NIU_ERRORS.get(err, ("http", f"erro {err}"))
                if code == "rate_limit":
                    raise RateLimited(f"NiuTrans: {msg}", retry_after=10)
                raise TranslationError(f"NiuTrans: {msg}", code)
            out.append(str(data.get("tgt_text", "")))
        return "\n".join(out)
