"""Microsoft Translator (Azure) via deep_translator — requer chave do usuário (opcional)."""
from __future__ import annotations

from ..languages import engine_lang
from .base import RateLimited, TranslationError, Translator


class MicrosoftTranslate(Translator):
    id = "microsoft"
    name = "Microsoft/Bing (chave Azure)"

    def __init__(self, api_key: str = "", region: str = ""):
        self.api_key = api_key
        self.region = region

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "informe a chave Azure em Opções > Tradução"
        try:
            import deep_translator  # noqa: F401
            return True, "ok"
        except ImportError:
            return False, "pip install deep-translator"

    def translate(self, text: str, src: str, tgt: str) -> str:
        try:
            from deep_translator import MicrosoftTranslator
        except ImportError as exc:
            raise TranslationError("deep-translator não instalado") from exc
        try:
            kw = {"region": self.region} if self.region else {}
            tr = MicrosoftTranslator(api_key=self.api_key, source=engine_lang("microsoft", src) if src else "auto",
                                     target=engine_lang("microsoft", tgt), **kw)
            return tr.translate(text)
        except Exception as exc:
            if "429" in str(exc) or "TooMany" in type(exc).__name__:
                raise RateLimited("Microsoft: limite") from exc
            raise TranslationError(f"Microsoft: {type(exc).__name__}") from exc
