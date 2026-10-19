"""OCR nativo do Windows 10/11 via pacote 'winocr' (experimental, NÃO testado)."""
from __future__ import annotations

import logging
import os
import time

from PIL import Image

from ..languages import alphabet
from .base import OcrBackend, OcrError, OcrResult, module_available

log = logging.getLogger(__name__)


class WindowsOcrBackend(OcrBackend):
    id = "winocr"
    name = "Windows OCR (experimental)"
    pip_hint = "pip install winocr   (somente Windows 10/11; requer pacote de idioma do Windows)"
    note = "Usa o motor do próprio Windows; rápido e sem baixar modelos. Não testado."

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if os.name != "nt":
            return False, "apenas no Windows"
        if module_available("winocr"):
            return True, "winocr ok"
        return False, "não instalado"

    def supports(self, alphabet_key: str) -> bool:
        return True

    def recognize(self, img: Image.Image, alphabet_key: str) -> OcrResult:
        try:
            import winocr  # type: ignore
        except ImportError as exc:
            raise OcrError("winocr não instalado (pip install winocr)") from exc
        lang = alphabet(alphabet_key).winocr
        t0 = time.perf_counter()
        try:
            out = winocr.recognize_pil_sync(img.convert("RGB"), lang)
        except Exception as exc:
            raise OcrError(f"Windows OCR falhou ({lang}); o pacote de idioma está instalado? {exc}") from exc
        if isinstance(out, dict):
            lines = out.get("lines") or []
            text = "\n".join(str(ln.get("text", "")) for ln in lines) if lines else str(out.get("text", ""))
        else:
            text = str(getattr(out, "text", "") or "")
        return OcrResult(text, None, self.id, (time.perf_counter() - t0) * 1000)
