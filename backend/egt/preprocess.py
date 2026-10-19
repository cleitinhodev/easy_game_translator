"""Pré-processamento de imagem para melhorar o OCR (PIL + numpy; OpenCV opcional).

Image preprocessing for OCR: upscale, grayscale, auto-invert, contrast, threshold, sharpen.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps


@dataclass
class PreprocessOptions:
    scale: float = 2.0            # 1.0–3.0
    grayscale: bool = True
    auto_invert: bool = True      # texto claro sobre fundo escuro → escuro sobre claro
    contrast: bool = False        # autocontraste (+ CLAHE se opencv estiver instalado)
    threshold: bool = False       # binarização de Otsu
    sharpen: bool = False
    pad: int = 6                  # borda extra (ajuda o Tesseract)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "PreprocessOptions":
        data = data or {}
        kw = {}
        for f in fields(cls):
            if f.name in data:
                kw[f.name] = data[f.name]
        o = cls(**kw)
        try:
            o.scale = max(1.0, min(3.0, float(o.scale)))
            o.pad = max(0, min(50, int(o.pad)))
        except (TypeError, ValueError):
            o.scale, o.pad = 2.0, 6
        return o

    def is_identity(self) -> bool:
        return (self.scale == 1.0 and not any((self.grayscale, self.auto_invert, self.contrast,
                                               self.threshold, self.sharpen)) and self.pad == 0)


def otsu_threshold(gray: np.ndarray) -> int:
    """Limiar de Otsu (0–255) para um array uint8 2D."""
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 127
    sum_all = np.dot(np.arange(256), hist)
    w_b = np.cumsum(hist)
    w_f = total - w_b
    sum_b = np.cumsum(hist * np.arange(256))
    with np.errstate(divide="ignore", invalid="ignore"):
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
    between = np.nan_to_num(between)
    return int(np.argmax(between))


def should_invert(gray: Image.Image) -> bool:
    """True se o fundo for escuro (média das bordas + do centro < 128)."""
    a = np.asarray(gray, dtype=np.uint8)
    if a.size == 0:
        return False
    h, w = a.shape
    b = max(1, min(h, w) // 10)
    border = np.concatenate([a[:b].ravel(), a[-b:].ravel(), a[:, :b].ravel(), a[:, -b:].ravel()])
    return float(border.mean()) < 118.0


def _clahe(gray: Image.Image) -> Image.Image:
    try:
        import cv2  # type: ignore
        arr = np.asarray(gray, dtype=np.uint8)
        out = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(arr)
        return Image.fromarray(out)
    except Exception:
        return ImageOps.autocontrast(gray, cutoff=1)


def preprocess(img: Image.Image, opts: PreprocessOptions) -> Image.Image:
    """Aplica as opções em ordem: escala → cinza → inversão → contraste → nitidez → limiar → borda."""
    out = img.convert("RGB") if img.mode not in ("RGB", "L") else img
    if opts.scale and opts.scale != 1.0:
        w, h = out.size
        out = out.resize((max(1, int(w * opts.scale)), max(1, int(h * opts.scale))), Image.LANCZOS)
    need_gray = opts.grayscale or opts.auto_invert or opts.contrast or opts.threshold
    if need_gray:
        out = ImageOps.grayscale(out)
    if opts.auto_invert and out.mode == "L" and should_invert(out):
        out = ImageOps.invert(out)
    if opts.contrast and out.mode == "L":
        out = _clahe(out)
    if opts.sharpen:
        out = out.filter(ImageFilter.UnsharpMask(radius=1.5, percent=160, threshold=2))
    if opts.threshold and out.mode == "L":
        arr = np.asarray(out, dtype=np.uint8)
        t = otsu_threshold(arr)
        out = Image.fromarray(((arr > t) * 255).astype(np.uint8), "L")
    if opts.pad:
        fill: Any = 255 if out.mode == "L" and (opts.auto_invert or opts.threshold) else \
            _edge_color(out)
        out = ImageOps.expand(out, border=opts.pad, fill=fill)
    return out


def _edge_color(img: Image.Image):
    a = np.asarray(img)
    edge = np.concatenate([a[0].reshape(-1, a.shape[-1]) if a.ndim == 3 else a[0].reshape(-1, 1),
                           a[-1].reshape(-1, a.shape[-1]) if a.ndim == 3 else a[-1].reshape(-1, 1)])
    med = np.median(edge, axis=0)
    if a.ndim == 3:
        return tuple(int(v) for v in med)
    return int(med[0])
