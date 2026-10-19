"""PaddleOCR (experimental, NÃO testado) — melhor opção para CJK em fontes difíceis."""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np
from PIL import Image

from ..languages import alphabet
from .base import OcrBackend, OcrError, OcrResult, boxes_to_text, module_available

log = logging.getLogger(__name__)


class PaddleOcrBackend(OcrBackend):
    id = "paddleocr"
    name = "PaddleOCR (experimental)"
    pip_hint = "pip install paddleocr paddlepaddle"
    note = "Experimental: a API do PaddleOCR muda entre versões; não foi testado."

    def __init__(self, settings: Optional[dict] = None):
        super().__init__(settings)
        self._engines: dict[str, object] = {}

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if module_available("paddleocr") and module_available("paddle"):
            return True, "paddleocr ok"
        return False, "não instalado"

    def supports(self, alphabet_key: str) -> bool:
        return alphabet(alphabet_key).paddle is not None

    def _engine(self, alphabet_key: str):
        lang = alphabet(alphabet_key).paddle
        if not lang:
            raise OcrError("PaddleOCR não suporta esse alfabeto.")
        if lang in self._engines:
            return self._engines[lang]
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:
            raise OcrError("PaddleOCR não instalado (pip install paddleocr paddlepaddle)") from exc
        try:
            try:
                eng = PaddleOCR(lang=lang, use_textline_orientation=False)  # 3.x
            except TypeError:
                eng = PaddleOCR(lang=lang, use_angle_cls=False, show_log=False)  # 2.x
        except Exception as exc:
            raise OcrError(f"Falha ao iniciar o PaddleOCR: {exc}") from exc
        self._engines[lang] = eng
        return eng

    def warmup(self, alphabet_key: str) -> None:
        self._engine(alphabet_key)

    def recognize(self, img: Image.Image, alphabet_key: str) -> OcrResult:
        eng = self._engine(alphabet_key)
        arr = np.asarray(img.convert("RGB"))
        t0 = time.perf_counter()
        items = []
        try:
            if hasattr(eng, "predict"):  # 3.x
                for page in eng.predict(arr):  # type: ignore[attr-defined]
                    polys = page.get("rec_polys") if hasattr(page, "get") else None
                    texts = page.get("rec_texts") if hasattr(page, "get") else None
                    scores = page.get("rec_scores") if hasattr(page, "get") else None
                    if polys is None or texts is None:
                        continue
                    for p, t, s in zip(polys, texts, scores if scores is not None else [None] * len(texts)):
                        items.append((np.asarray(p).tolist(), t, None if s is None else float(s)))
            else:  # 2.x
                res = eng.ocr(arr, cls=False)  # type: ignore[attr-defined]
                for page in res or []:
                    for box, (text, score) in page or []:
                        items.append((box, text, float(score)))
        except Exception as exc:
            raise OcrError(f"PaddleOCR falhou: {exc}") from exc
        text, conf = boxes_to_text(items)
        return OcrResult(text, conf, self.id, (time.perf_counter() - t0) * 1000)
