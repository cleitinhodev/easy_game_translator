"""OCR real com Tesseract (pulado se não estiver instalado) + registro de motores."""
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from egt import ocr
from egt.change import is_garbage
from egt.languages import clean_ocr_text
from egt.preprocess import PreprocessOptions, preprocess


def _font(size):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def sample(text="Hello World 123", light_on_dark=False):
    bg, fg = ((15, 15, 35), (245, 245, 245)) if light_on_dark else ((250, 250, 250), (10, 10, 10))
    im = Image.new("RGB", (460, 80), bg)
    ImageDraw.Draw(im).text((12, 14), text, font=_font(40), fill=fg)
    return im


def test_registry_status_never_crashes():
    st = ocr.status()
    assert {s["id"] for s in st} == {"tesseract", "rapidocr", "easyocr", "paddleocr", "winocr"}
    for s in st:
        assert isinstance(s["available"], bool) and s["pip_hint"]


def test_missing_backend_gives_friendly_error():
    reg = ocr.OcrRegistry()
    for cls in ocr.BACKENDS.values():
        ok, _ = cls.availability()
        if not ok:
            with pytest.raises(ocr.OcrError) as e:
                reg.get(cls.id)
            assert "pip install" in str(e.value) or "Instale" in str(e.value) or "indispon" in str(e.value)
    with pytest.raises(ocr.OcrError):
        reg.get("nope")


@pytest.mark.skipif(not (shutil.which("tesseract") or ocr.find_tesseract()), reason="tesseract ausente")
@pytest.mark.parametrize("dark", [False, True])
def test_tesseract_reads_generated_image(dark):
    reg = ocr.OcrRegistry(lambda: {"tesseract_psm": 6})
    be = reg.get("tesseract")
    img = preprocess(sample(light_on_dark=dark), PreprocessOptions())
    res = be.recognize(img, "abc(EN)")
    text = clean_ocr_text(res.text, "abc(EN)")
    assert "Hello" in text and "World" in text and "123" in text, text
    assert res.confidence and res.confidence > 50 and not is_garbage(text)


@pytest.mark.skipif(not ocr.find_tesseract(), reason="tesseract ausente")
def test_tesseract_missing_language_message():
    be = ocr.OcrRegistry().get("tesseract")
    langs = be.installed_languages()
    if "jpn" in langs:
        pytest.skip("jpn instalado")
    with pytest.raises(ocr.OcrError) as e:
        be.recognize(sample(), "あ")
    assert "jpn" in str(e.value)


def test_registry_falls_back_to_first_usable(monkeypatch):
    """Sem Tesseract instalado, o padrão passa a ser o primeiro motor utilizável."""
    reg = ocr.OcrRegistry()
    monkeypatch.setattr(ocr, "find_tesseract", lambda configured="": None)
    monkeypatch.setattr(ocr.RapidOcrBackend, "availability", classmethod(lambda cls: (True, "ok")))
    assert not reg.usable("tesseract")
    assert reg.first_usable("tesseract") == "rapidocr"
    assert reg.first_usable("rapidocr") == "rapidocr"
    monkeypatch.setattr(ocr.RapidOcrBackend, "availability", classmethod(lambda cls: (False, "x")))
    for cls in ocr.BACKENDS.values():
        if cls is not ocr.RapidOcrBackend:
            monkeypatch.setattr(cls, "availability", classmethod(lambda c: (False, "x")))
    assert reg.first_usable("tesseract") is None
