"""RapidOCR (onnxruntime) — rápido, offline, ótimo em fontes de jogo (EN/ZH)."""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np
from PIL import Image

from ..languages import alphabet
from .base import OcrBackend, OcrError, OcrResult, boxes_to_text, module_available

log = logging.getLogger(__name__)


def _user_models() -> dict:
    """Modelos próprios do usuário (det.onnx / rec.onnx / cls.onnx na pasta de componentes). Sem arquivos: {} (padrão)."""
    try:
        from ..components.store import get_store
        d = get_store().dir_for("rapidocr")
        out = {}
        for key, name in (("det_model_path", "det.onnx"), ("rec_model_path", "rec.onnx"), ("cls_model_path", "cls.onnx")):
            if (d / name).is_file():
                out[key] = str(d / name)
        return out
    except Exception:  # noqa: BLE001
        return {}


class RapidOcrBackend(OcrBackend):
    id = "rapidocr"
    name = "RapidOCR"
    pip_hint = "pip install rapidocr-onnxruntime"
    note = "Offline e rápido. Modelos padrão: inglês/latim + chinês."

    def __init__(self, settings: Optional[dict] = None):
        super().__init__(settings)
        self._engine = None
        self._v2 = False

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if module_available("rapidocr_onnxruntime"):
            return True, "rapidocr-onnxruntime ok"
        if module_available("rapidocr"):
            return True, "rapidocr ok"
        return False, "não instalado"

    def supports(self, alphabet_key: str) -> bool:
        return alphabet(alphabet_key).rapid is not None

    def _load(self):
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
            self._engine = RapidOCR(**_user_models())
        except ImportError:
            try:
                from rapidocr import RapidOCR  # type: ignore  # v2+
                self._engine, self._v2 = RapidOCR(**_user_models()), True
            except ImportError as exc:
                raise OcrError("RapidOCR não instalado (pip install rapidocr-onnxruntime)") from exc
        except Exception as exc:
            raise OcrError(f"Falha ao iniciar o RapidOCR: {exc}") from exc
        return self._engine

    def warmup(self, alphabet_key: str) -> None:
        self._load()

    def recognize(self, img: Image.Image, alphabet_key: str) -> OcrResult:
        if not self.supports(alphabet_key):
            raise OcrError("RapidOCR (modelo padrão) não lê esse alfabeto — use EasyOCR ou Tesseract.")
        eng = self._load()
        arr = np.asarray(img.convert("RGB"))
        t0 = time.perf_counter()
        try:
            out = eng(arr)
        except Exception as exc:
            raise OcrError(f"RapidOCR falhou: {exc}") from exc
        items = []
        if self._v2:
            boxes = getattr(out, "boxes", None)
            txts = getattr(out, "txts", None)
            scores = getattr(out, "scores", None)
            if boxes is not None and txts is not None:
                items = list(zip(boxes.tolist() if hasattr(boxes, "tolist") else boxes, txts,
                                 scores if scores is not None else [None] * len(txts)))
        else:
            result = out[0] if isinstance(out, tuple) else out
            for row in result or []:
                box, text, score = row[0], row[1], row[2]
                items.append((box, text, float(score)))
        text, conf = boxes_to_text(items)
        return OcrResult(text, conf, self.id, (time.perf_counter() - t0) * 1000)
