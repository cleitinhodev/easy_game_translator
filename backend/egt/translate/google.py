"""Google Tradutor via deep_translator (padrão, sem chave)."""
from __future__ import annotations

from ..languages import engine_lang
from .base import RateLimited, TranslationError, Translator, split_chunks


class GoogleTranslate(Translator):
    id = "google"
    name = "Google (deep-translator)"

    def available(self) -> tuple[bool, str]:
        try:
            import deep_translator  # noqa: F401
            return True, "ok"
        except ImportError:
            return False, "pip install deep-translator"

    def translate(self, text: str, src: str, tgt: str) -> str:
        try:
            from deep_translator import GoogleTranslator
            from deep_translator.exceptions import TooManyRequests, TranslationNotFound
        except ImportError as exc:
            raise TranslationError("deep-translator não instalado") from exc
        s, t = (engine_lang("google", src) if src else "auto"), engine_lang("google", tgt)
        out = []
        for chunk in split_chunks(text, 4500):
            try:
                try:
                    res = GoogleTranslator(source=s, target=t).translate(chunk)
                except Exception as exc:
                    if isinstance(exc, (TooManyRequests,)):
                        raise
                    if s != "auto" and "No support for the provided language" in str(exc):
                        res = GoogleTranslator(source="auto", target=t).translate(chunk)  # origem rara
                    else:
                        raise
            except TooManyRequests as exc:
                raise RateLimited("Google: muitas requisições") from exc
            except TranslationNotFound as exc:
                raise TranslationError("Google: sem tradução") from exc
            except TranslationError:
                raise
            except Exception as exc:
                raise TranslationError(f"Google: {type(exc).__name__}: {exc}") from exc
            out.append(res or "")
        return "\n".join(out)
