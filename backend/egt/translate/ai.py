"""Tradução por IA (OPCIONAL, desligada por padrão): Gemini (REST) e Ollama (HTTP local)."""
from __future__ import annotations

import logging
import re
from typing import Callable

from ..languages import LANG_NAMES, normalize_lang
from .base import RateLimited, TranslationError, Translator

log = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest")   # ai.google.dev/gemini-api/docs/models
_MODEL_RE = re.compile(r"[A-Za-z0-9._-]{1,80}")

# códigos de erro (a interface traduz): sem a chave, a resposta do servidor nunca é repassada (pode ecoar dados)
AI_MESSAGES = {
    "no_key": "Gemini: sem chave de API",
    "bad_key": "Chave inválida ou sem permissão",
    "model_unavailable": "Modelo não disponível para a sua chave. Escolha gemini-3.5-flash-lite.",
    "bad_model": "Nome de modelo inválido",
    "rate_limit": "Limite de uso atingido (cota do Google). Espere um pouco ou confira o uso no Google AI Studio.",
    "network": "Sem conexão com o servidor",
    "empty": "Resposta vazia ou bloqueada",
    "http": "Erro do servidor",
    "ollama_down": "Ollama não encontrado — o servidor está rodando?",
    "ollama_model_missing": "Modelo não encontrado no Ollama (baixe com: ollama pull <modelo>)",
}


class AiError(TranslationError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(AI_MESSAGES.get(code, code) + (f" ({detail})" if detail else ""))
        self.code = code


class AiRateLimited(RateLimited):
    def __init__(self, retry_after: float = 30):
        super().__init__(AI_MESSAGES["rate_limit"], retry_after=retry_after)
        self.code = "rate_limit"


def gemini_http_error(status: int) -> AiError:
    if status == 404:
        return AiError("model_unavailable", "HTTP 404")
    if status in (400, 401, 403):
        return AiError("bad_key", f"HTTP {status}")
    return AiError("http", f"HTTP {status}")


def build_prompt(text: str, src: str, tgt: str, context: str = "") -> str:
    tgt_name = LANG_NAMES.get(tgt) or LANG_NAMES.get(normalize_lang(tgt), tgt)
    src_part = f"from {src} " if src else ""
    ctx = f"\nGame context / glossary: {context.strip()}" if context.strip() else ""
    return (
        f"You are a video game localization translator. Translate the on-screen text {src_part}"
        f"to {tgt_name} ({tgt}). The text came from OCR and may contain small recognition errors; "
        "fix them silently. Keep character names, tokens like XQ0A1B2CQX and formatting untouched. "
        "Answer ONLY with the translation, no quotes or notes." + ctx + f"\n\nText:\n{text}"
    )


class GeminiTranslate(Translator):
    id = "gemini"
    name = "Gemini (IA)"

    def __init__(self, key_provider: Callable[[], str], model: str = DEFAULT_GEMINI_MODEL,
                 context_provider: Callable[[], str] = lambda: "", timeout: float = 20.0):
        self._key = key_provider
        self.model = model
        self._ctx = context_provider
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self._key() else (False, "informe a chave (Opções > IA) ou GEMINI_API_KEY")

    def translate(self, text: str, src: str, tgt: str) -> str:
        import requests
        if not _MODEL_RE.fullmatch(self.model or ""):
            raise AiError("bad_model")
        key = self._key()                      # lida só agora (cifrada em disco) e descartada no fim da chamada
        if not key:
            raise AiError("no_key")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {"contents": [{"parts": [{"text": build_prompt(text, src, tgt, self._ctx())}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024}}
        try:
            r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AiError("network", type(exc).__name__) from None      # sem a URL/headers no traceback
        finally:
            key = ""
        if r.status_code == 429:
            raise AiRateLimited(30)
        if r.status_code != 200:
            raise gemini_http_error(r.status_code)  # não registra o corpo (pode ecoar dados)
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (ValueError, KeyError, IndexError) as exc:
            raise AiError("empty") from exc


class OllamaTranslate(Translator):
    id = "ollama"
    name = "Ollama (IA local)"
    online = False

    def __init__(self, url: str = "http://localhost:11434", model: str = "llama3.2",
                 context_provider: Callable[[], str] = lambda: "", timeout: float = 60.0):
        self.url = (url or "").rstrip("/")
        self.model = model
        self._ctx = context_provider
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self.url and self.model else (False, "configure URL e modelo")

    def translate(self, text: str, src: str, tgt: str) -> str:
        import requests
        body = {"model": self.model, "prompt": build_prompt(text, src, tgt, self._ctx()),
                "stream": False, "options": {"temperature": 0.2}}
        try:
            r = requests.post(f"{self.url}/api/generate", json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AiError("ollama_down", type(exc).__name__) from exc
        if r.status_code == 404:
            raise AiError("ollama_model_missing", self.model)
        if r.status_code != 200:
            raise AiError("http", f"HTTP {r.status_code}")
        try:
            return str(r.json()["response"]).strip()
        except (ValueError, KeyError) as exc:
            raise AiError("empty") from exc
