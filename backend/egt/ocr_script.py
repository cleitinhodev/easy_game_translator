"""Script de OCR (4.1 beta): o usuário escolhe um arquivo que LÊ a imagem capturada no lugar dos motores de OCR.

É o mesmo papel de um motor embutido (Tesseract, RapidOCR…): recebe a imagem da região e devolve o texto (e, se
quiser, a confiança 0–100). Todo o resto continua igual: a miniatura é feita pelo próprio app a partir da captura,
e o texto devolvido passa pela mesma limpeza, regras de substituição, filtros (mínimo de letras/confiança),
detecção de mudança e tradução (tradutores, IA ou script de tradução) que o texto dos motores embutidos.

Contrato (versão 1) — canal único e duplo:

  ENTRADA  (stdin, UTF-8, um único JSON):
      {"version": 1, "kind": "ocr", "mode": "single" | "dual",
       "images": [ {"channel": "uni" | "a" | "b",
                    "path": ".../uni.png",          # imagem JÁ PRÉ-PROCESSADA (a mesma que os motores embutidos recebem)
                    "width": 1320, "height": 160,
                    "raw_path": ".../uni_raw.png",  # captura ORIGINAL da tela, sem pré-processamento
                    "raw_width": 660, "raw_height": 80} ],      # canal duplo: SEMPRE 2 imagens, [canal A, canal B]
       "channels": ["uni"] ou ["a", "b"],
       "alphabet": "abc(EN)", "ocr_lang": "eng", "lang_hint": "en", "cjk": false,
       "preprocess": {"scale": 2.0, "grayscale": true, ...}}
      (opcional nas configurações: "base64"/"raw_base64" com o PNG em base64 em cada imagem)

  SAÍDA    (stdout, UTF-8), uma das formas:
      1) JSON: {"outputs": ["texto A"(, "texto B")]}
               cada item pode ser um objeto {"text": "...", "confidence": 87.5}  (confiança 0–100, opcional)
               ou use a lista paralela "confidences": [87.5, null]
               {"error": "mensagem"} avisa um erro ao usuário
      2) Texto puro: canal único → todo o texto; canal duplo → os dois textos separados por uma linha só com  ---
      Uma saída por imagem, na mesma ordem. Saída vazia ("") = nenhum texto na imagem (como um motor embutido).

Os arquivos PNG ficam numa pasta temporária privada criada para cada leitura e são apagados logo depois.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

from PIL import Image

from .languages import alphabet as get_alphabet
from .ocr.base import OcrError, OcrResult
from .userscript import CONTRACT_VERSION, SEPARATOR, ScriptError, ScriptRunner, execute

log = logging.getLogger(__name__)

ENGINE_ID = "script"
DEFAULT_TIMEOUT = 20.0
TMP_PREFIX = "egt-ocrtmp-"
MAX_TEXT = 20000              # caracteres por saída (o resto é cortado)
MAX_SIDE = 8192               # imagens maiores são reduzidas antes de ir para o script


class OcrScriptError(OcrError):
    """Erro do script de OCR com código (mesmos códigos do script de tradução). Mensagem: 'Script OCR [código]: …'."""

    def __init__(self, err: ScriptError):
        self.code = err.code
        self.detail = err.detail
        super().__init__(f"Script OCR [{err.code}]" + (f": {err.detail}" if err.detail else ""))


@dataclass
class OcrScriptRun:
    results: list[OcrResult]
    ms: float = 0.0
    format: str = "json"
    stderr: str = ""
    payload: dict = field(default_factory=dict)


# ------------------------------------------------------------------ saída
def _conf(v) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    c = float(v)
    if c != c:                      # NaN
        return None
    if c < 0:
        return None
    if c <= 1.0:                    # 0–1 (como RapidOCR/EasyOCR) → 0–100
        c *= 100.0
    return min(100.0, c)


def parse_ocr_output(raw: str, n: int) -> tuple[list[tuple[str, Optional[float]]], str]:
    """[(texto, confiança|None)] × n e o formato ("json" | "text"). Levanta ScriptError."""
    text = (raw or "").lstrip("\ufeff").strip()
    if not text:
        return [("", None)] * n, "text"           # nada impresso = nenhum texto lido (igual a um motor embutido)
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            if data.get("error"):
                raise ScriptError("script_error", str(data["error"])[:300])
            outs = data.get("outputs")
            if isinstance(outs, (str, dict)):
                outs = [outs]
            if not isinstance(outs, list):
                raise ScriptError("bad_output", '"outputs" deve ser uma lista de textos')
            confs = data.get("confidences")
            if not isinstance(confs, list) or len(confs) != len(outs):
                confs = [None] * len(outs)
            res: list[tuple[str, Optional[float]]] = []
            for o, c in zip(outs, confs):
                if isinstance(o, dict):
                    t = o.get("text", "")
                    c = o.get("confidence", c)
                else:
                    t = o
                if t is None:
                    t = ""
                if not isinstance(t, str):
                    raise ScriptError("bad_output", '"outputs" deve ser uma lista de textos')
                res.append((t.strip()[:MAX_TEXT], _conf(c)))
            if len(res) != n:
                raise ScriptError("count", f"{len(res)}/{n}")
            return res, "json"
    if n == 1:
        return [(text[:MAX_TEXT], None)], "text"
    parts, cur = [], []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip() == SEPARATOR:
            parts.append("\n".join(cur).strip())
            cur = []
        else:
            cur.append(line)
    parts.append("\n".join(cur).strip())
    if len(parts) != n:
        raise ScriptError("count", f"{len(parts)}/{n}")
    return [(p[:MAX_TEXT], None) for p in parts], "text"


# ------------------------------------------------------------------ entrada
def _fit(img: Image.Image) -> Image.Image:
    if max(img.size) <= MAX_SIDE:
        return img
    f = MAX_SIDE / max(img.size)
    return img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))))


def _png(img: Image.Image, path: str) -> bytes:
    im = _fit(img)
    if im.mode not in ("RGB", "L", "RGBA"):
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "PNG", compress_level=1)
    data = buf.getvalue()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return data


def build_payload(tmpdir: str, items: Sequence[tuple[str, Image.Image, Image.Image]], alphabet_key: str,
                  mode: str, channels: Sequence[str], preprocess: Optional[dict] = None,
                  with_base64: bool = False) -> dict:
    """Grava os PNGs em `tmpdir` e monta o JSON do contrato. items = [(canal, captura original, pré-processada)]."""
    a = get_alphabet(alphabet_key)
    images = []
    for ch, raw, pre in items:
        safe = ch if ch in ("uni", "a", "b") else "img"
        p_pre = os.path.join(tmpdir, f"{safe}.png")
        p_raw = os.path.join(tmpdir, f"{safe}_raw.png")
        d_pre = _png(pre, p_pre)
        d_raw = _png(raw, p_raw)
        im = {"channel": ch, "path": p_pre, "width": _fit(pre).width, "height": _fit(pre).height,
              "raw_path": p_raw, "raw_width": _fit(raw).width, "raw_height": _fit(raw).height}
        if with_base64:
            im["base64"] = base64.b64encode(d_pre).decode("ascii")
            im["raw_base64"] = base64.b64encode(d_raw).decode("ascii")
        images.append(im)
    return {"version": CONTRACT_VERSION, "kind": "ocr", "mode": mode, "images": images,
            "channels": list(channels), "alphabet": a.key, "ocr_lang": a.tesseract, "lang_hint": a.hint,
            "cjk": bool(a.cjk), "preprocess": dict(preprocess or {})}


def run_ocr_script(path: str, items: Sequence[tuple[str, Image.Image, Image.Image]], alphabet_key: str,
                   mode: str = "", channels: Optional[Sequence[str]] = None, timeout: float = DEFAULT_TIMEOUT,
                   preprocess: Optional[dict] = None, with_base64: bool = False) -> OcrScriptRun:
    """Roda o script de OCR uma vez com 1 ou 2 imagens. Não confere o hash (veja OcrScriptBackend)."""
    if not items or len(items) > 2:
        raise ScriptError("count", str(len(items)))
    mode = mode or ("dual" if len(items) == 2 else "single")
    channels = list(channels or [c for c, _, _ in items])
    tmpdir = tempfile.mkdtemp(prefix=TMP_PREFIX)          # pasta privada (0700 no Linux; %TEMP% do usuário no Windows)
    try:
        payload = build_payload(tmpdir, items, alphabet_key, mode, channels, preprocess, with_base64)
        raw, stderr, ms = execute(path, payload, timeout)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    parsed, fmt = parse_ocr_output(raw, len(items))
    results = [OcrResult(t, c, ENGINE_ID, ms) for t, c in parsed]
    return OcrScriptRun(results, ms, fmt, stderr, payload)


def _is_ours(p: str) -> bool:
    """Só apaga o que o próprio app cria: pasta comum (não link), do usuário atual, só com PNGs dentro."""
    try:
        if os.path.islink(p) or not os.path.isdir(p):
            return False
        if hasattr(os, "getuid") and os.stat(p).st_uid != os.getuid():
            return False
        for e in os.scandir(p):
            if not e.is_file(follow_symlinks=False) or not e.name.lower().endswith(".png"):
                return False
        return True
    except OSError:
        return False


def sweep_temp(max_age_s: float = 3600.0) -> int:
    """Apaga pastas temporárias esquecidas (ex.: o app foi fechado à força no meio de uma leitura)."""
    n = 0
    base = tempfile.gettempdir()
    now = time.time()
    try:
        for name in os.listdir(base):
            if not name.startswith(TMP_PREFIX):
                continue
            p = os.path.join(base, name)
            try:
                if now - os.path.getmtime(p) > max_age_s and _is_ours(p):
                    shutil.rmtree(p, ignore_errors=True)
                    n += 1
            except OSError:
                continue
    except OSError:
        pass
    return n


class OcrScriptBackend:
    """Motor de OCR "Script": mesma interface dos embutidos (supports/recognize) + recognize_channels para ler
    o(s) canal(is) do ciclo numa única execução do script."""

    id = ENGINE_ID
    name = "Script"

    def __init__(self, settings, preprocess_provider=None):
        self.settings = settings
        self.runner = ScriptRunner(settings, "ocr_script", DEFAULT_TIMEOUT)
        self._pre = preprocess_provider or (lambda: {})
        self.last_format = ""
        self.last_stderr = ""

    def active(self) -> bool:
        return self.runner.active()

    def supports(self, alphabet_key: str) -> bool:
        return True

    def warmup(self, alphabet_key: str) -> None:
        return None

    def run(self, items, alphabet_key: str, mode: str = "", channels=None) -> OcrScriptRun:
        """Levanta OcrScriptError (subclasse de OcrError) com mensagem 'Script OCR [código]: …'."""
        try:
            r = self.runner.guarded(lambda path: run_ocr_script(
                path, items, alphabet_key, mode, channels, self.runner.timeout(), self._pre(),
                bool(self.settings.get("ocr_script.send_base64", False))))
        except ScriptError as exc:
            log.warning("script de OCR: %s", exc)
            raise OcrScriptError(exc) from None
        self.last_format, self.last_stderr = r.format, r.stderr
        return r

    def recognize_channels(self, items, alphabet_key: str, mode: str = "", channels=None) -> list[OcrResult]:
        return self.run(items, alphabet_key, mode, channels).results

    def recognize(self, img: Image.Image, alphabet_key: str, raw: Optional[Image.Image] = None,
                  channel: str = "uni") -> OcrResult:
        return self.recognize_channels([(channel, raw if raw is not None else img, img)], alphabet_key, "single",
                                       [channel])[0]

    def info(self) -> dict:
        d = self.runner.info()
        d["send_base64"] = bool(self.settings.get("ocr_script.send_base64", False))
        d["last_format"] = self.last_format
        return d


# ------------------------------------------------------------------ imagens de exemplo (botão "Testar script")
SAMPLE_TEXTS = {"uni": "Hello, adventurer!\nThe gate is closed.", "a": "Hello, adventurer!\nThe gate is closed.",
                "b": "Nina: Let's go to the castle!"}


def _font(size: int):
    from PIL import ImageFont
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Arial.ttf", "segoeuib.ttf",
                 "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antigo
        return ImageFont.load_default()


def sample_image(channel: str) -> Image.Image:
    """Caixa de diálogo de jogo (fundo azul-marinho, texto claro) — igual ao que se captura de verdade."""
    from PIL import ImageDraw
    text = SAMPLE_TEXTS.get(channel, SAMPLE_TEXTS["uni"])
    font = _font(30)
    lines = text.split("\n")
    w, h = 640, 34 + 44 * len(lines)
    img = Image.new("RGB", (w, h), (28, 31, 68))
    d = ImageDraw.Draw(img)
    d.rectangle([3, 3, w - 4, h - 4], outline=(120, 130, 210), width=2)
    for i, ln in enumerate(lines):
        d.text((22, 16 + 44 * i), ln, font=font, fill=(242, 242, 242))
    return img


def redact_payload(payload: dict) -> dict:
    """Cópia do JSON para mostrar na tela: caminhos viram só o nome do arquivo e o base64 é encurtado."""
    out = json.loads(json.dumps(payload))
    for im in out.get("images", []):
        for k in ("path", "raw_path"):
            if im.get(k):
                im[k] = ".../" + os.path.basename(im[k])
        for k in ("base64", "raw_base64"):
            if im.get(k):
                im[k] = im[k][:24] + "…"
    return out
