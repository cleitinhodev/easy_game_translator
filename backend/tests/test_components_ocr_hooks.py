"""As integrações dos componentes com os motores de OCR não mudam nada se o usuário não colocou arquivos."""
import sys

from egt.components.store import ComponentsStore, set_store, user_tessdata
from egt.ocr import rapid, tesseract


def test_no_user_files_means_no_change(tmp_path):
    st = ComponentsStore(tmp_path / "c.json")
    st.data["root"] = str(tmp_path / "comp")
    set_store(st)
    try:
        assert user_tessdata(st) is None
        assert rapid._user_models() == {}
        assert tesseract._user_tessdata() is None or not list(tesseract._user_tessdata().glob("*.traineddata"))
    finally:
        set_store(None)


def test_user_tessdata_detected_only_with_traineddata(tmp_path):
    st = ComponentsStore(tmp_path / "c.json")
    st.data["root"] = str(tmp_path / "comp")
    d = st.ensure("tessdata")
    assert user_tessdata(st) is None
    (d / "readme.txt").write_text("x")
    assert user_tessdata(st) is None
    (d / "por.traineddata").write_bytes(b"x")
    assert user_tessdata(st) == d


def test_rapid_user_models_follow_the_files_present(tmp_path):
    st = ComponentsStore(tmp_path / "c.json")
    st.data["root"] = str(tmp_path / "comp")
    set_store(st)
    try:
        d = st.ensure("rapidocr")
        assert rapid._user_models() == {}
        (d / "det.onnx").write_bytes(b"1")
        assert list(rapid._user_models()) == ["det_model_path"]
        (d / "rec.onnx").write_bytes(b"1")
        assert set(rapid._user_models()) == {"det_model_path", "rec_model_path"}
    finally:
        set_store(None)
