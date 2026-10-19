import time

from PIL import Image, ImageDraw

from egt.ocr.base import OcrError, OcrResult, boxes_to_text
from egt.pipeline import Pipeline, PipelineConfig
from egt.preprocess import PreprocessOptions
from egt.translate.base import TranslationResult


class FakeOcr:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def supports(self, a):
        return True

    def recognize(self, img, alphabet):
        self.calls += 1
        t = self.texts[min(self.calls - 1, len(self.texts) - 1)]
        if isinstance(t, Exception):
            raise t
        return OcrResult(t, 90.0, "fake", 1.0)


class Cap:
    """Captura falsa: troca de imagem quando `variant` muda."""

    def __init__(self):
        self.variant = 0
        self.calls = 0

    def __call__(self, bbox):
        self.calls += 1
        im = Image.new("RGB", (200, 60), (10, 10, 30))
        ImageDraw.Draw(im).rectangle([10, 10, 20 + 40 * self.variant, 40], fill=(250, 250, 250))
        return im


def make(ocr, cap=None, translate=None, **cfg):
    cap = cap or Cap()
    calls = []

    def tr(text, src, tgt):
        calls.append((text, src, tgt))
        return TranslationResult(f"PT:{text}", engine="fake", src=src, tgt=tgt)

    base = dict(channels={"uni": (0, 0, 200, 60)}, interval=0.2, stable_ms=0, preprocess=PreprocessOptions(scale=1))
    base.update(cfg)
    p = Pipeline(cap, lambda eid: ocr, translate or tr, config=PipelineConfig(**base))
    return p, cap, calls


def wait_for(p, pred, timeout=5.0):
    seen = []
    end = time.time() + timeout
    while time.time() < end:
        seen += p.drain()
        if pred(seen):
            return seen
        time.sleep(0.02)
    return seen


def kinds(evs):
    return [e.kind for e in evs]


def test_translate_now_single_shot():
    ocr = FakeOcr(["Hello brave world"])
    p, cap, calls = make(ocr)
    p.translate_now()
    evs = wait_for(p, lambda s: any(e.kind == "translation" for e in s))
    tr = [e for e in evs if e.kind == "translation"]
    assert tr and tr[0].data["translated"] == "PT:Hello brave world" and tr[0].channel == "uni"
    assert any(e.kind == "ocr" for e in evs)
    assert calls[0][1] == "en" and calls[0][2] == "pt"
    time.sleep(0.2)
    assert not p.busy()


def test_continuous_skips_unchanged_image_and_text():
    ocr = FakeOcr(["Same text here"])
    p, cap, calls = make(ocr)
    p.start()
    wait_for(p, lambda s: any(e.kind == "translation" for e in s))
    time.sleep(0.8)          # vários ciclos com imagem idêntica
    p.stop(wait=True)
    assert ocr.calls == 1, "OCR deve rodar só uma vez com imagem parada"
    assert len(calls) == 1


def test_changed_image_same_text_translates_once():
    ocr = FakeOcr(["Same text here"])
    p, cap, calls = make(ocr)
    p.start()
    wait_for(p, lambda s: any(e.kind == "translation" for e in s))
    cap.variant = 2          # imagem muda, mas o OCR devolve o mesmo texto
    time.sleep(0.8)
    p.stop(wait=True)
    assert ocr.calls >= 2 and len(calls) == 1


def test_new_text_translates_again_and_debounce():
    ocr = FakeOcr(["Hel", "Hello wor", "Hello world again"])
    p, cap, calls = make(ocr, stable_ms=300, min_chars=3)
    p.start()
    for v in (1, 2, 3):
        cap.variant = v
        time.sleep(0.25)
    wait_for(p, lambda s: any(e.kind == "translation" for e in s), 5)
    p.stop(wait=True)
    texts = [c[0] for c in calls]
    assert texts == ["Hello world again"], texts   # só a versão final foi traduzida


def test_garbage_and_low_conf_are_ignored():
    ocr = FakeOcr(["!!", "ab"])
    p, cap, calls = make(ocr)
    p.translate_now()
    evs = wait_for(p, lambda s: any(e.kind == "empty" for e in s))
    assert not calls and any(e.kind == "empty" for e in evs)


def test_ocr_error_is_reported_not_raised():
    ocr = FakeOcr([OcrError("sem dados de idioma")])
    p, cap, calls = make(ocr)
    p.start()
    evs = wait_for(p, lambda s: any(e.kind == "error" for e in s))
    p.stop(wait=True)
    assert any(e.kind == "error" and "sem dados" in e.data["message"] for e in evs)


def test_translation_failure_retries():
    attempts = []

    def flaky(text, src, tgt):
        attempts.append(text)
        if len(attempts) == 1:
            return TranslationResult("", ok=False, error="down")
        return TranslationResult("ok:" + text, engine="fake")

    ocr = FakeOcr(["Retry this line"])
    p, cap, _ = make(ocr, translate=flaky)
    p.start()
    evs = wait_for(p, lambda s: sum(e.kind == "translation" and e.data.get("ok") for e in s) >= 1, 8)
    p.stop(wait=True)
    assert len(attempts) >= 2
    assert any(e.kind == "translation" and e.data["ok"] for e in evs)


def test_dual_channels_and_no_regions():
    ocr = FakeOcr(["Channel text A", "Channel text B"])
    p, cap, calls = make(ocr, channels={"a": (0, 0, 200, 60), "b": (0, 100, 200, 160)})
    p.translate_now()
    evs = wait_for(p, lambda s: sum(e.kind == "translation" for e in s) >= 2)
    assert {e.channel for e in evs if e.kind == "translation"} == {"a", "b"}
    p2, *_ = make(FakeOcr(["x"]), channels={})
    p2.translate_now()
    evs = wait_for(p2, lambda s: any(e.kind == "error" for e in s))
    assert any(e.kind == "error" for e in evs)


def test_stop_and_restart_cleanly():
    p, cap, calls = make(FakeOcr(["Some text for you"]))
    assert p.start() and not p.start()
    time.sleep(0.2)
    p.stop(wait=True)
    assert not p.running
    assert p.start()
    p.stop(wait=True)


def test_boxes_to_text_orders_lines():
    items = [([[100, 5], [150, 5], [150, 25], [100, 25]], "world", 0.9),
             ([[10, 6], [60, 6], [60, 26], [10, 26]], "Hello", 0.8),
             ([[10, 50], [90, 50], [90, 70], [10, 70]], "Line two", 0.7)]
    text, conf = boxes_to_text(items)
    assert text == "Hello world\nLine two" and 79 < conf < 81
