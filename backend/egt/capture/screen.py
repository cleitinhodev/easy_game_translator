"""Captura de regiões da tela usando coordenadas de TODOS os monitores.

Screen region capture with virtual-desktop coordinates (negative values allowed,
e.g. a monitor placed to the left of the primary one).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional, Sequence

from PIL import Image

log = logging.getLogger(__name__)

BBox = tuple  # (x1, y1, x2, y2)


def enable_dpi_awareness() -> None:
    """Windows: faz o Tk e o mss usarem os mesmos pixels físicos. Seguro em outros SO."""
    if os.name != "nt":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception as exc:  # pragma: no cover
        log.debug("DPI awareness indisponível: %s", exc)


def normalize_bbox(bbox: Sequence[float]) -> Optional[BBox]:
    """Ordena os cantos e valida. Retorna None se a área for inválida/minúscula."""
    try:
        x1, y1, x2, y2 = (int(round(float(v))) for v in bbox[:4])
    except (TypeError, ValueError, IndexError):
        return None
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return (x1, y1, x2, y2)


def _new_mss():
    """mss.MSS (novo) ou mss.mss (versões antigas)."""
    import mss
    return getattr(mss, "MSS", None)() if hasattr(mss, "MSS") else mss.mss()


def list_monitors() -> list[dict]:
    """Monitores físicos [{left, top, width, height}] (sem o 'monitor 0' virtual)."""
    try:
        with _new_mss() as sct:
            return [dict(m) for m in sct.monitors[1:]]
    except Exception as exc:
        log.debug("mss indisponível para listar monitores: %s", exc)
        return []


def virtual_screen() -> Optional[dict]:
    """Retângulo que cobre todos os monitores (ou None se desconhecido)."""
    try:
        with _new_mss() as sct:
            return dict(sct.monitors[0])
    except Exception:
        return None


class ScreenGrabber:
    """Captura com mss (rápido). Cada thread cria sua própria instância do mss
    (o mss não é seguro entre threads). Se falhar, usa ImageGrab(all_screens=True)."""

    def __init__(self, prefer_mss: bool = True):
        self.prefer_mss = prefer_mss
        self._local = threading.local()
        self.backend = "mss" if prefer_mss else "pil"
        self._mss_failed = False

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = _new_mss()
            self._local.sct = sct
        return sct

    def grab(self, bbox: Sequence[float]) -> Image.Image:
        box = normalize_bbox(bbox)
        if box is None:
            raise ValueError(f"região inválida: {bbox!r}")
        x1, y1, x2, y2 = box
        if self.prefer_mss and not self._mss_failed:
            try:
                shot = self._sct().grab({"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1})
                self.backend = "mss"
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            except Exception as exc:
                log.warning("mss falhou (%s); usando PIL.ImageGrab", exc)
                self._mss_failed = True
                self._local.sct = None
        from PIL import ImageGrab
        self.backend = "pil"
        try:
            return ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")
        except TypeError:  # Pillow/Linux antigos sem all_screens
            return ImageGrab.grab(bbox=box).convert("RGB")

    def close(self) -> None:
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            try:
                sct.close()
            except Exception:
                pass
            self._local.sct = None
