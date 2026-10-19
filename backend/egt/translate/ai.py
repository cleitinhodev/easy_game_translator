"""Tradução por IA (OPCIONAL, desligada por padrão): Gemini (REST) e Ollama (HTTP local)."""
from __future__ import annotations

import logging
from typing import Callable

from ..languages import LANG_NAMES, normalize_lang
from .base import RateLimited, TranslationError, Translator

log = logging.getLogger(__name__)


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

    def __init__(self, key_provider: Callable[[], str], model: str = "gemini-2.5-flash",
                 context_provider: Callable[[], str] = lambda: "", timeout: float = 20.0):
        self._key = key_provider
        self.model = model
        self._ctx = context_provider
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        return (True, "ok") if self._key() else (False, "informe a chave (Opções > IA) ou GEMINI_API_KEY")

    def translate(self, text: str, src: str, tgt: str) -> str:
        import requests
        key = self._key()
        if not key:
            raise TranslationError("Gemini: sem chave de API")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {"contents": [{"parts": [{"text": build_prompt(text, src, tgt, self._ctx())}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024}}
        try:
            r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TranslationError(f"Gemini: {type(exc).__name__}") from exc
        if r.status_code == 429:
            raise RateLimited("Gemini: cota/limite", retry_after=30)
        if r.status_code != 200:
            raise TranslationError(f"Gemini: HTTP {r.status_code}")  # não registra o corpo (pode ecoar dados)
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (ValueError, KeyError, IndexError) as exc:
            raise TranslationError("Gemini: resposta vazia/bloqueada") from exc


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
            raise TranslationError(f"Ollama: {type(exc).__name__} (o servidor está rodando?)") from exc
        if r.status_code != 200:
            raise TranslationError(f"Ollama: HTTP {r.status_code}")
        try:
            return str(r.json()["response"]).strip()
        except (ValueError, KeyError) as exc:
            raise TranslationError("Ollama: resposta inválida") from exc
