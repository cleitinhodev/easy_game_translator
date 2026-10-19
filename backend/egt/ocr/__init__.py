"""Registro dos motores de OCR (todos opcionais, importados sob demanda)."""
from __future__ import annotations

import logging
import threading
from typing import Optional

from .base import OcrBackend, OcrError, OcrResult, boxes_to_text
from .easy import EasyOcrBackend
from .paddle import PaddleOcrBackend
from .rapid import RapidOcrBackend
from .tesseract import TesseractBackend, find_tesseract
from .winocr import WindowsOcrBackend

log = logging.getLogger(__name__)

BACKENDS: dict[str, type[OcrBackend]] = {
    cls.id: cls for cls in (TesseractBackend, RapidOcrBackend, EasyOcrBackend,
                            PaddleOcrBackend, WindowsOcrBackend)
}


def status() -> list[dict]:
    """[{id, name, available, detail, pip_hint, note}] para a tela de configurações."""
    out = []
    for cls in BACKENDS.values():
        try:
            ok, detail = cls.availability()
        except Exception as exc:  # nunca quebra
            ok, detail = False, f"erro: {exc}"
        out.append({"id": cls.id, "name": cls.name, "available": ok, "detail": detail,
                    "pip_hint": cls.pip_hint, "note": cls.note})
    return out


class OcrRegistry:
    """Cria e guarda uma instância por motor; `options` vem das configurações."""

    def __init__(self, options_provider=None):
        self._opts = options_provider or (lambda: {})
        self._inst: dict[str, OcrBackend] = {}
        self._lock = threading.Lock()

    def get(self, engine_id: str) -> OcrBackend:
        cls = BACKENDS.get(engine_id)
        if cls is None:
            raise OcrError(f"Motor de OCR desconhecido: {engine_id}")
        ok, detail = cls.availability()
        if not ok:
            raise OcrError(f"{cls.name} indisponível: {detail}. Instale com: {cls.pip_hint}")
        with self._lock:
            inst = self._inst.get(engine_id)
            if inst is None:
                inst = cls(self._opts())
                self._inst[engine_id] = inst
            return inst

    # ordem de preferência quando o motor escolhido não está utilizável
    FALLBACK_ORDER = ("tesseract", "rapidocr", "easyocr", "paddleocr", "winocr")

    def usable(self, engine_id: str) -> bool:
        """Instalado E pronto para uso (o Tesseract também precisa do executável)."""
        cls = BACKENDS.get(engine_id)
        if cls is None:
            return False
        try:
            ok, _ = cls.availability()
            if ok and engine_id == "tesseract":
                ok = find_tesseract(self._opts().get("tesseract_path", "")) is not None
        except Exception:
            return False
        return ok

    def first_usable(self, preferred: str = "") -> Optional[str]:
        """O motor preferido se estiver utilizável; senão o primeiro utilizável; senão None."""
        order = [preferred] if preferred else []
        order += [e for e in self.FALLBACK_ORDER if e != preferred]
        order += [e for e in BACKENDS if e not in order]
        for eid in order:
            if self.usable(eid):
                return eid
        return None

    def get_or_fallback(self, engine_id: str) -> OcrBackend:
        """Como get(), mas se o motor escolhido não estiver utilizável usa o primeiro que estiver."""
        if not self.usable(engine_id):
            alt = self.first_usable(engine_id)
            if alt and alt != engine_id:
                log.warning("OCR '%s' indisponível; usando '%s'", engine_id, alt)
                engine_id = alt
        return self.get(engine_id)

    def reset(self, engine_id: Optional[str] = None) -> None:
        """Descarta instâncias (ex.: depois de mudar o caminho do Tesseract)."""
        with self._lock:
            if engine_id:
                self._inst.pop(engine_id, None)
            else:
                self._inst.clear()


__all__ = ["BACKENDS", "OcrBackend", "OcrError", "OcrResult", "OcrRegistry", "status",
           "find_tesseract", "boxes_to_text", "TesseractBackend"]
