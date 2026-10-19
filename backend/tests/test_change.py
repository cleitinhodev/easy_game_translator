from PIL import Image, ImageDraw

from egt.change import (ImageChangeDetector, TextStabilizer, is_garbage, normalize_text,
                        texts_similar)


def _frame(text_box=None):
    im = Image.new("RGB", (300, 80), (20, 20, 40))
    if text_box:
        ImageDraw.Draw(im).rectangle(text_box, fill=(240, 240, 240))
    return im


def test_identical_frames_unchanged():
    d = ImageChangeDetector()
    assert d.changed(_frame()) is True      # primeira vez
    assert d.changed(_frame()) is False
    assert d.changed(_frame()) is False


def test_small_text_change_detected():
    d = ImageChangeDetector()
    d.changed(_frame())
    assert d.changed(_frame((10, 30, 120, 50))) is True


def test_size_change_detected():
    d = ImageChangeDetector()
    d.changed(_frame())
    assert d.changed(Image.new("RGB", (200, 80), (20, 20, 40))) is True


def test_normalize_and_similar():
    assert normalize_text("  Hello \n  world ") == "Hello world"
    assert texts_similar("Hello world", "hello  WORLD")
    assert texts_similar("The quick brown fox jumps over", "The quick brown fox jumps ouer")
    assert not texts_similar("Hello world", "Goodbye moon")
    assert not texts_similar("a", "b")


def test_garbage():
    assert is_garbage("")
    assert is_garbage("a")
    assert is_garbage("!!! ??? ...")
    assert is_garbage("|| __ ~~ a1")
    assert not is_garbage("Hello there")
    assert not is_garbage("你好", min_chars=1)


def test_stabilizer_waits_and_emits_once():
    s = TextStabilizer(stable_ms=500, max_wait_ms=4000)
    assert s.feed("Hel", 0.0) is None
    assert s.feed("Hello", 0.3) is None       # ainda mudando
    assert s.feed("Hello wor", 0.6) is None
    assert s.feed("Hello world", 0.9) is None
    assert s.poll(1.2) is None
    assert s.poll(1.5) == "Hello world"       # estável por 0.6s
    assert s.poll(2.0) is None
    assert s.feed("Hello world", 2.1) is None   # igual ao último emitido
    assert s.feed("Hello wor1d", 2.2) is None   # ruído de OCR


def test_stabilizer_new_line_emits():
    s = TextStabilizer(stable_ms=100)
    assert s.feed("First line here", 0.0) is None
    assert s.feed("First line here", 0.2) == "First line here"
    assert s.feed("Something else entirely", 0.3) is None
    assert s.poll(0.5) == "Something else entirely"


def test_stabilizer_max_wait():
    s = TextStabilizer(stable_ms=1000, max_wait_ms=2000)
    out = None
    t = 0.0
    for i in range(20):
        out = s.feed("text number %d here" % i, t) or out
        t += 0.3
    assert out is not None    # nunca ficou estável, mas passou do máximo


def test_stabilizer_forget_last_allows_repeat():
    s = TextStabilizer(stable_ms=0)
    assert s.feed("Same sentence", 0.0) == "Same sentence"
    s.reset(forget_last=True)
    assert s.feed("Same sentence", 1.0) == "Same sentence"
