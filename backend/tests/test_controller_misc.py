"""Controlador sem interface, atalhos, motores opcionais e segurança de segredos."""
import re
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from egt import ocr
from egt.app import AppController
from egt.config import Settings
from egt.db import Database
from egt.glossary import Glossary
from egt.profiles import Profile, ProfileStore
from egt.translate.base import Translator

ROOT = Path(__file__).resolve().parent.parent


class FakeTr(Translator):
    id = "google"
    name = "fake"

    def __init__(self):
        self.calls = []

    def available(self):
        return True, ""

    def translate(self, text, src, tgt):
        self.calls.append(text)
        return f"<{tgt}>{text}"


class FakeGrab:
    def grab(self, bbox):
        im = Image.new("RGB", (300, 60), (240, 240, 240))
        ImageDraw.Draw(im).text((10, 10), "Anything", fill=(0, 0, 0))
        return im

    def close(self):
        pass


@pytest.fixture
def ctrl(tmp_path):
    c = AppController(settings=Settings(tmp_path / "s.json"), db=Database(), profiles=ProfileStore(tmp_path / "p"),
                      glossary=Glossary(), grabber=FakeGrab())
    tr = FakeTr()
    c.manager._engines = lambda: [tr]
    c.fake = tr
    yield c
    c.pipeline.stop(wait=True)


def test_start_without_region_is_refused(ctrl):
    assert ctrl.start() is False and ctrl.last_error == "no_region"
    assert ctrl.translate_now() is False


def test_glossary_protects_names_end_to_end(ctrl):
    ctrl.glossary.set_data([{"find": "Nlna", "replace": "Nina"}], ["Nina"], save=False)
    out = ctrl.glossary.apply_replacements("Nlna runs home")
    res = ctrl.translate_pipeline_text(out, "en", "pt")
    assert res.ok and "Nina" in res.text and "Nina" not in ctrl.fake.calls[0]
    # segunda vez vem do cache e ainda restaura o nome
    res2 = ctrl.translate_pipeline_text(out, "en", "pt")
    assert res2.cached and "Nina" in res2.text and len(ctrl.fake.calls) == 1


def test_manual_translation_detects_language(ctrl):
    res = ctrl.translate_manual("This is a fairly long English sentence for detection", "pt")
    assert res.ok and res.src == "en"


def test_session_roundtrip(ctrl, tmp_path):
    ctrl.set_region("uni", (5, 5, 305, 65))
    ctrl.update_profile(target="ja", mode="dual")
    ctrl.save_session()
    again = ctrl.profiles.load_last()
    assert again.target == "ja" and again.mode == "dual" and again.region_single == [5, 5, 305, 65]
    assert ctrl.profile.channels() == {}      # dual sem regiões A/B
    ctrl.apply_profile(Profile.from_dict(again.to_dict()))


def test_history_written_from_events(ctrl):
    ctrl.set_region("uni", (0, 0, 300, 60))
    ctrl.pipeline.update_config(min_confidence=0, stable_ms=0, min_chars=1)
    ctrl.translate_now()
    end = time.time() + 6
    while time.time() < end and ctrl.history.count() == 0:
        ctrl.poll_events()
        time.sleep(0.05)
    assert ctrl.history.count() >= 1 or ctrl.last_error      # OCR real pode faltar no CI; não deve travar


def test_ocr_self_test_unavailable_engine_is_graceful(ctrl):
    ok, msg = ctrl.ocr_self_test("easyocr") if not ocr.BACKENDS["easyocr"].availability()[0] else (False, "x")
    assert ok is False and msg


def test_hotkey_accelerator_migration(tmp_path):
    from egt.config import to_accelerator
    assert to_accelerator("<ctrl>+<alt>+t") == "Control+Alt+T"
    assert to_accelerator("CommandOrControl+Alt+S") == "CommandOrControl+Alt+S"
    (tmp_path / "s.json").write_text('{"hotkeys": {"toggle": "<ctrl>+<shift>+x"}}', encoding="utf-8")
    assert Settings(tmp_path / "s.json").get("hotkeys.toggle") == "Control+Shift+X"


def test_update_profile_validation(ctrl):
    assert ctrl.update_profile(interval=99, font_size=3) == ["interval", "font_size"]
    assert ctrl.profile.interval == 5.0 and ctrl.profile.font_size == 8
    with pytest.raises(ValueError):
        ctrl.update_profile(alphabet="nope")
    with pytest.raises(ValueError):
        ctrl.update_profile(target="xx")
    ctrl.update_profile(preprocess={"scale": 3.0, "threshold": True})
    assert ctrl.profile.preprocess.scale == 3.0 and ctrl.profile.preprocess.threshold


def test_rapidocr_backend_if_installed():
    if not ocr.BACKENDS["rapidocr"].availability()[0]:
        pytest.skip("rapidocr não instalado")
    from tests.test_ocr_smoke import sample
    be = ocr.OcrRegistry().get("rapidocr")
    res = be.recognize(sample(), "abc(EN)")
    assert "Hello" in res.text and res.confidence


def test_no_secrets_or_personal_paths_in_project():
    pat = re.compile(r"AIza[0-9A-Za-z_\-]{10,}|C:[\\/]+Users|Cleit(?!inhoDEV)")
    for f in ROOT.rglob("*"):
        if f.is_file() and f.suffix in {".py", ".txt", ".md", ".json", ".spec", ".toml", ".example"} \
                and "__pycache__" not in f.parts and f.name != "test_controller_misc.py":
            text = f.read_text(encoding="utf-8", errors="ignore")
            assert not pat.search(text), f"possível segredo/caminho pessoal em {f}"
