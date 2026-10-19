"""A miniatura do painel 'Original' acompanha cada captura nova (e só ela)."""
import time
from dataclasses import replace

from egt.pipeline import PREVIEW_MAX_W, make_preview
from egt.ocr.base import OcrResult
from PIL import Image

from tests.test_pipeline import Cap, FakeOcr, make, wait_for


def previews(evs, ch=None):
    return [e for e in evs if e.kind == "preview" and (ch is None or e.channel == ch)]


def test_make_preview_is_small_jpeg_data_url():
    big = Image.new("RGB", (1600, 400), (200, 30, 30))
    pv = make_preview(big)
    assert pv["image"].startswith("data:image/jpeg;base64,")
    assert pv["width"] == 1600 and pv["height"] == 400
    import base64, io
    im = Image.open(io.BytesIO(base64.b64decode(pv["image"].split(",", 1)[1])))
    assert im.width == PREVIEW_MAX_W and im.height == 120
    assert len(pv["image"]) < 40_000          # payload leve


def test_changed_image_emits_different_preview_same_text():
    """Mesmo texto no OCR (nenhum evento 'ocr' novo), mas a imagem mudou: a miniatura tem que mudar."""
    cap = Cap()
    p, _, _ = make(FakeOcr(["Same subtitle text"]), cap, interval=0.1, stable_ms=0)
    p.start()
    try:
        seen = wait_for(p, lambda ev: bool(previews(ev)))
        first = previews(seen)[0]
        assert first.data["seq"] == 1
        time.sleep(0.5)
        assert not previews(p.drain())          # imagem parada: nenhuma miniatura repetida (sem payload à toa)
        cap.variant = 3                         # imagem muda, texto igual
        seen = wait_for(p, lambda ev: bool(previews(ev)))
        second = previews(seen)[0]
        assert second.data["image"] != first.data["image"]
        assert second.data["seq"] == 2
        assert not [e for e in seen if e.kind == "ocr"]     # texto idêntico: só a miniatura foi atualizada
    finally:
        p.stop(wait=True)


def test_forced_refresh_sends_preview_even_if_unchanged():
    cap = Cap()
    p, _, _ = make(FakeOcr(["Hello there friend"]), cap, interval=0.1, stable_ms=0)
    p.start()
    try:
        wait_for(p, lambda ev: bool(previews(ev)))
        time.sleep(0.4); p.drain()
        p.refresh("full")
        seen = wait_for(p, lambda ev: bool(previews(ev)))
        assert previews(seen)
    finally:
        p.stop(wait=True)


def test_preview_sent_when_ocr_fails_or_is_empty():
    cap = Cap()
    p, _, _ = make(FakeOcr([".."]), cap, interval=0.1, stable_ms=0)       # lixo => evento 'empty', mas a captura mudou
    p.start()
    try:
        seen = wait_for(p, lambda ev: bool(previews(ev)))
        assert previews(seen)
    finally:
        p.stop(wait=True)


def test_dual_channel_previews_are_per_channel():
    cap = Cap()
    p, _, _ = make(FakeOcr(["Alpha text here", "Beta text here"]), cap, interval=0.1, stable_ms=0,
             channels={"a": (0, 0, 200, 60), "b": (0, 70, 200, 130)})
    p.start()
    try:
        seen = wait_for(p, lambda ev: {e.channel for e in previews(ev)} >= {"a", "b"})
        assert {e.channel for e in previews(seen)} == {"a", "b"}
    finally:
        p.stop(wait=True)
