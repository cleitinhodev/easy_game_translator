"""Tesseract (pytesseract) com detecção automática do executável."""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from ..languages import alphabet
from .base import OcrBackend, OcrError, OcrResult, module_available

log = logging.getLogger(__name__)


def common_paths() -> list[Path]:
    """Locais comuns do tesseract (Windows/macOS/Linux)."""
    out: list[Path] = []
    if os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            out.append(Path(base) / "Tesseract-OCR" / "tesseract.exe")
            out.append(Path(base) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
        out += [Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
                Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe")]
    else:
        out += [Path("/usr/bin/tesseract"), Path("/usr/local/bin/tesseract"),
                Path("/opt/homebrew/bin/tesseract")]
    return out


def find_tesseract(configured: str = "") -> Optional[str]:
    """Ordem: caminho configurado → PATH → locais comuns. Retorna None se não achar."""
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return str(p)
    which = shutil.which("tesseract")
    if which:
        return which
    for p in common_paths():
        if p.is_file():
            return str(p)
    try:        # último recurso: Tesseract "portátil" colocado/baixado na pasta de componentes do usuário
        from ..components.store import get_store
        d = get_store().dir_for("tesseract")
        for cand in (d / "tesseract.exe", d / "Tesseract-OCR" / "tesseract.exe", d / "tesseract"):
            if cand.is_file():
                return str(cand)
    except Exception:  # noqa: BLE001
        pass
    return None


def _user_tessdata() -> Optional[Path]:
    """Pasta tessdata do usuário (componentes) se existir e tiver idiomas; senão None (comportamento original)."""
    try:
        from ..components.store import get_store, user_tessdata
        return user_tessdata(get_store())
    except Exception:  # noqa: BLE001
        return None


class TesseractBackend(OcrBackend):
    id = "tesseract"
    name = "Tesseract"
    pip_hint = "pip install pytesseract  +  instalar o Tesseract-OCR (UB Mannheim no Windows)"
    note = "Padrão, offline, leve. Bom para fontes limpas."

    def __init__(self, settings: Optional[dict] = None):
        super().__init__(settings)
        self._pt = None
        self._cmd: Optional[str] = None
        self._langs: Optional[set[str]] = None

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if not module_available("pytesseract"):
            return False, "pytesseract não instalado"
        return True, "pytesseract ok"  # o executável é checado em tempo de uso

    def supports(self, alphabet_key: str) -> bool:
        return True

    def _setup(self):
        if self._pt is not None:
            return self._pt
        try:
            import pytesseract
        except ImportError as exc:
            raise OcrError("pytesseract não instalado (pip install pytesseract)") from exc
        cmd = find_tesseract(self.options.get("tesseract_path", ""))
        if not cmd:
            raise OcrError("Tesseract não encontrado. Instale-o e/ou informe o caminho em Opções > OCR.")
        pytesseract.pytesseract.tesseract_cmd = cmd
        self._cmd = cmd
        self._pt = pytesseract
        return pytesseract

    def version(self) -> str:
        pt = self._setup()
        try:
            return str(pt.get_tesseract_version())
        except Exception as exc:
            raise OcrError(f"Falha ao executar o Tesseract: {exc}") from exc

    def installed_languages(self) -> set[str]:
        if self._langs is None:
            pt = self._setup()
            try:
                self._langs = set(pt.get_languages(config=""))
                ud = _user_tessdata()
                if ud is not None:
                    self._langs |= {f.stem for f in ud.glob("*.traineddata")}
            except Exception as exc:
                raise OcrError(f"Não consegui listar idiomas do Tesseract: {exc}") from exc
        return self._langs

    def warmup(self, alphabet_key: str) -> None:
        self.version()
        self._check_lang(alphabet(alphabet_key).tesseract)

    def _check_lang(self, lang: str) -> None:
        if lang not in self.installed_languages():
            raise OcrError(
                f"Dados de idioma '{lang}' não instalados no Tesseract. "
                f"Baixe {lang}.traineddata (github.com/tesseract-ocr/tessdata) e coloque na pasta tessdata.")

    def recognize(self, img: Image.Image, alphabet_key: str) -> OcrResult:
        pt = self._setup()
        lang = alphabet(alphabet_key).tesseract
        self._check_lang(lang)
        psm = int(self.options.get("tesseract_psm", 6) or 6)
        t0 = time.perf_counter()
        try:
            cfg = f"--psm {psm}"
            ud = _user_tessdata()
            if ud is not None and all((ud / f"{part}.traineddata").is_file() for part in lang.split("+")):
                cfg += f' --tessdata-dir "{ud.as_posix()}"'      # idioma baixado pelo gerenciador de componentes
            data = pt.image_to_data(img, lang=lang, config=cfg, output_type=pt.Output.DICT)
        except Exception as exc:
            raise OcrError(f"Tesseract falhou: {exc}") from exc
        text, conf = _data_to_text(data)
        return OcrResult(text, conf, self.id, (time.perf_counter() - t0) * 1000)


def _data_to_text(data: dict) -> tuple[str, Optional[float]]:
    """Reconstrói linhas a partir do image_to_data e calcula a confiança média."""
    lines: dict[tuple, list[str]] = {}
    confs: list[float] = []
    n = len(data.get("text", []))
    for i in range(n):
        word = str(data["text"][i]).strip()
        if not word:
            continue
        try:
            c = float(data["conf"][i])
        except (TypeError, ValueError):
            c = -1.0
        if c >= 0:
            confs.append(c)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
    text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
    return text, (sum(confs) / len(confs) if confs else None)
