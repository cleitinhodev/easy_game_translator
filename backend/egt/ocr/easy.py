"""EasyOCR — muitos idiomas (JA/KO/AR/HI...), baixa modelos na primeira vez; GPU opcional."""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np
from PIL import Image

from ..languages import alphabet
from .base import OcrBackend, OcrError, OcrResult, boxes_to_text, module_available

log = logging.getLogger(__name__)


class EasyOcrBackend(OcrBackend):
    id = "easyocr"
    name = "EasyOCR"
    pip_hint = "pip install easyocr   (puxa o PyTorch, ~2 GB)"
    note = "Excelente em fonte estilizada, japonês, coreano, árabe. Pesado; 1ª execução baixa modelos."

    def __init__(self, settings: Optional[dict] = None):
        super().__init__(settings)
        self._readers: dict[tuple, object] = {}

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if module_available("easyocr"):
            return True, "easyocr ok"
        return False, "não instalado"

    def supports(self, alphabet_key: str) -> bool:
        return True

    def _reader(self, alphabet_key: str):
        langs = tuple(alphabet(alphabet_key).easy)
        if langs in self._readers:
            return self._readers[langs]
        try:
            import easyocr  # type: ignore
        except ImportError as exc:
            raise OcrError("EasyOCR não instalado (pip install easyocr)") from exc
        try:
            log.info("Carregando EasyOCR %s (pode baixar modelos)...", langs)
            kw = {}
            try:        # modelos na pasta de componentes (só se houver arquivos lá; senão o padrão do EasyOCR)
                from ..components.store import get_store
                md = get_store().dir_for("easyocr")
                if md.is_dir() and any(md.glob("*.pth")):
                    kw["model_storage_directory"] = str(md)
            except Exception:  # noqa: BLE001
                pass
            reader = easyocr.Reader(list(langs), gpu=bool(self.options.get("easyocr_gpu", False)),
                                    verbose=False, **kw)
        except Exception as exc:
            raise OcrError(f"Falha ao iniciar o EasyOCR para {langs}: {exc}") from exc
        self._readers[langs] = reader
        return reader

    def warmup(self, alphabet_key: str) -> None:
        self._reader(alphabet_key)

    def recognize(self, img: Image.Image, alphabet_key: str) -> OcrResult:
        reader = self._reader(alphabet_key)
        arr = np.asarray(img.convert("RGB"))
        t0 = time.perf_counter()
        try:
            res = reader.readtext(arr)  # type: ignore[attr-defined]
        except Exception as exc:
            raise OcrError(f"EasyOCR falhou: {exc}") from exc
        items = [(box, text, float(conf)) for box, text, conf in res]
        text, conf = boxes_to_text(items)
        return OcrResult(text, conf, self.id, (time.perf_counter() - t0) * 1000)
