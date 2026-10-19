"""Detecção de mudança (imagem e texto), debounce de digitação e filtro de lixo do OCR.

Change detection (image + text), typewriter-effect debounce and OCR garbage filter.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Optional

import numpy as np
from PIL import Image

SIG_SIZE = (96, 96)


def image_signature(img: Image.Image) -> np.ndarray:
    """Assinatura leve: imagem reduzida em tons de cinza (float32)."""
    small = img.convert("L").resize(SIG_SIZE, Image.BILINEAR)
    return np.asarray(small, dtype=np.float32)


class ImageChangeDetector:
    """Compara com o último quadro que disparou OCR (referência).

    Mudou se a diferença média absoluta >= mean_thr OU se uma fração mínima de
    pixels mudou bastante (pega mudanças pequenas, como uma palavra nova).
    """

    def __init__(self, mean_thr: float = 1.0, pixel_thr: float = 40.0, frac_thr: float = 0.004):
        self.mean_thr = mean_thr
        self.pixel_thr = pixel_thr
        self.frac_thr = frac_thr
        self._ref: Optional[np.ndarray] = None
        self._shape: Optional[tuple] = None

    def reset(self) -> None:
        self._ref = None

    def changed(self, img: Image.Image) -> bool:
        sig = image_signature(img)
        size = img.size
        if self._ref is None or self._shape != size:
            self._ref, self._shape = sig, size
            return True
        diff = np.abs(sig - self._ref)
        if float(diff.mean()) >= self.mean_thr or float((diff >= self.pixel_thr).mean()) >= self.frac_thr:
            self._ref = sig
            return True
        return False


# --------------------------------------------------------------------- texto

def normalize_text(text: str) -> str:
    """Normalização para comparar/cachear: NFKC + espaços colapsados."""
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def texts_similar(a: str, b: str, threshold: float = 0.96) -> bool:
    """Textos iguais, ou quase (ruído de OCR de 1–2 caracteres)?"""
    na, nb = normalize_text(a).casefold(), normalize_text(b).casefold()
    if na == nb:
        return True
    if not na or not nb or threshold >= 1.0:
        return False
    if abs(len(na) - len(nb)) > max(2, int(0.08 * max(len(na), len(nb)))):
        return False
    return difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio() >= threshold


def is_garbage(text: str, min_chars: int = 3, min_alnum_ratio: float = 0.5) -> bool:
    """Texto curto demais ou com poucos caracteres alfanuméricos (lixo do OCR)."""
    t = re.sub(r"\s+", "", text or "")
    if not t:
        return True
    alnum = sum(1 for c in t if c.isalnum())
    if alnum < min_chars:
        return True
    return (alnum / len(t)) < min_alnum_ratio


class TextStabilizer:
    """Só libera o texto depois que ele ficou estável por `stable_ms`.

    - `feed(text, now)`: nova leitura do OCR.
    - `poll(now)`: chamada quando a imagem NÃO mudou (o texto pendente envelhece).
    Não libera de novo texto parecido com o último liberado.
    """

    def __init__(self, stable_ms: int = 450, max_wait_ms: int = 4000, similarity: float = 0.96):
        self.stable_s = max(0, stable_ms) / 1000.0
        self.max_wait_s = max(self.stable_s, max_wait_ms / 1000.0)
        self.similarity = similarity
        self.pending: Optional[str] = None
        self._since = 0.0          # quando o pendente apareceu estável
        self._first = 0.0          # quando começou a série de mudanças
        self.last_emitted: Optional[str] = None

    def reset(self, forget_last: bool = False) -> None:
        self.pending = None
        if forget_last:
            self.last_emitted = None

    def _maybe_emit(self, now: float) -> Optional[str]:
        if self.pending is None:
            return None
        aged = now - self._since >= self.stable_s
        overdue = now - self._first >= self.max_wait_s
        if aged or overdue:
            text, self.pending = self.pending, None
            if self.last_emitted is not None and texts_similar(text, self.last_emitted, self.similarity):
                return None
            self.last_emitted = text
            return text
        return None

    def feed(self, text: str, now: float) -> Optional[str]:
        if self.pending is None:
            if self.last_emitted is not None and texts_similar(text, self.last_emitted, self.similarity):
                return None
            self.pending, self._since, self._first = text, now, now
        elif not texts_similar(text, self.pending, self.similarity):
            self.pending, self._since = text, now      # ainda mudando (digitação)
        return self._maybe_emit(now)

    def poll(self, now: float) -> Optional[str]:
        return self._maybe_emit(now)
