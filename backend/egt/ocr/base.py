"""Interface comum dos motores de OCR + utilitários. / Pluggable OCR backend interface."""
from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from PIL import Image


class OcrError(Exception):
    """Falha esperada do OCR (motor ausente, idioma sem dados...). Mensagem amigável."""


@dataclass
class OcrResult:
    text: str
    confidence: Optional[float] = None   # 0–100, None se o motor não informa
    engine: str = ""
    elapsed_ms: float = 0.0


def module_available(name: str) -> bool:
    """Checa se um módulo pode ser importado SEM importá-lo (rápido, não quebra)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


class OcrBackend(ABC):
    """Cada motor importa suas bibliotecas só quando usado (lazy)."""

    id: str = ""
    name: str = ""
    pip_hint: str = ""
    note: str = ""

    def __init__(self, settings: Optional[dict] = None):
        self.options = dict(settings or {})

    @classmethod
    @abstractmethod
    def availability(cls) -> tuple[bool, str]:
        """(disponível?, detalhe curto). Nunca levanta exceção."""

    @abstractmethod
    def supports(self, alphabet_key: str) -> bool:
        """O motor lê esse alfabeto?"""

    @abstractmethod
    def recognize(self, img: Image.Image, alphabet_key: str) -> OcrResult:
        """Lê a imagem. Levanta OcrError para problemas esperados."""

    def warmup(self, alphabet_key: str) -> None:
        """Carrega modelos antes do primeiro uso (chamado em thread de trabalho)."""


def boxes_to_text(items: Iterable[tuple[Sequence[Sequence[float]], str, Optional[float]]]) -> tuple[str, Optional[float]]:
    """Junta caixas (polígono, texto, confiança) em linhas ordenadas.

    Usado por RapidOCR/EasyOCR/Paddle, que devolvem blocos soltos.
    Retorna (texto com \\n entre linhas, confiança média 0–100).
    """
    rows = []
    confs = []
    for box, text, conf in items:
        text = (text or "").strip()
        if not text:
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        rows.append({"x": min(xs), "yc": (min(ys) + max(ys)) / 2.0, "h": max(1.0, max(ys) - min(ys)), "t": text})
        if conf is not None:
            confs.append(float(conf))
    if not rows:
        return "", None
    rows.sort(key=lambda r: r["yc"])
    lines: list[list[dict]] = []
    for r in rows:
        if lines and abs(r["yc"] - lines[-1][-1]["yc"]) < 0.55 * max(r["h"], lines[-1][-1]["h"]):
            lines[-1].append(r)
        else:
            lines.append([r])
    out = []
    for ln in lines:
        ln.sort(key=lambda r: r["x"])
        out.append(" ".join(r["t"] for r in ln))
    conf = None
    if confs:
        conf = sum(confs) / len(confs)
        if conf <= 1.0:
            conf *= 100.0  # motores que devolvem 0–1
    return "\n".join(out), conf
