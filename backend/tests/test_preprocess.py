import numpy as np
from PIL import Image, ImageDraw

from egt.preprocess import PreprocessOptions, otsu_threshold, preprocess, should_invert


def _img(bg, fg, size=(120, 40)):
    im = Image.new("RGB", size, bg)
    ImageDraw.Draw(im).rectangle([20, 10, 100, 30], fill=fg)
    return im


def test_upscale_and_pad():
    out = preprocess(_img((255, 255, 255), (0, 0, 0)), PreprocessOptions(scale=2, pad=5))
    assert out.size == (120 * 2 + 10, 40 * 2 + 10)


def test_identity_keeps_size():
    o = PreprocessOptions(scale=1, grayscale=False, auto_invert=False, contrast=False,
                          threshold=False, sharpen=False, pad=0)
    assert o.is_identity()
    im = _img((10, 10, 10), (200, 200, 200))
    assert preprocess(im, o).size == im.size


def test_auto_invert_light_text_on_dark():
    dark = _img((10, 10, 30), (240, 240, 240))
    assert should_invert(dark.convert("L"))
    out = preprocess(dark, PreprocessOptions(scale=1, pad=0))
    a = np.asarray(out)
    assert a[0, 0] > 200  # fundo agora claro


def test_no_invert_dark_text_on_light():
    light = _img((250, 250, 250), (10, 10, 10))
    assert not should_invert(light.convert("L"))
    a = np.asarray(preprocess(light, PreprocessOptions(scale=1, pad=0)))
    assert a[0, 0] > 200


def test_otsu_bimodal():
    arr = np.concatenate([np.full(500, 30, np.uint8), np.full(500, 220, np.uint8)]).reshape(25, 40)
    t = otsu_threshold(arr)
    assert 30 <= t < 220


def test_threshold_binary():
    out = preprocess(_img((20, 20, 20), (230, 230, 230)),
                     PreprocessOptions(scale=1, threshold=True, pad=0))
    vals = set(np.unique(np.asarray(out)).tolist())
    assert vals <= {0, 255}


def test_options_roundtrip_and_clamp():
    o = PreprocessOptions.from_dict({"scale": 9, "threshold": True, "bogus": 1})
    assert o.scale == 3.0 and o.threshold
    assert PreprocessOptions.from_dict(o.to_dict()) == o
    assert PreprocessOptions.from_dict(None).scale == 2.0
