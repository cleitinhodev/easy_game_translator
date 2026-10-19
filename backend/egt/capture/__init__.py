"""Captura de tela multi-monitor (mss, com fallback para PIL.ImageGrab)."""
from .screen import ScreenGrabber, enable_dpi_awareness, list_monitors, virtual_screen, normalize_bbox

__all__ = ["ScreenGrabber", "enable_dpi_awareness", "list_monitors", "virtual_screen", "normalize_bbox"]
