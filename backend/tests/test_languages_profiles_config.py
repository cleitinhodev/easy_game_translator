from egt import config, paths
from egt.capture.screen import normalize_bbox
from egt.languages import (ALPHABETS, TARGET_LANGUAGES, clean_ocr_text, detect_source, engine_lang,
                           label_to_code, lang_label, normalize_lang)
from egt.profiles import Profile, ProfileStore


def test_17_targets_and_9_alphabets():
    assert len(TARGET_LANGUAGES) == 17 and len(ALPHABETS) == 9
    assert {a.tesseract for a in ALPHABETS.values()} == {
        "eng", "por", "chi_sim", "hin", "ara", "ben", "rus", "jpn", "kor"}


def test_labels_roundtrip():
    for code, _ in TARGET_LANGUAGES:
        assert label_to_code(lang_label(code)) == code
    assert label_to_code("Português") == "pt"


def test_normalize_and_engine_codes():
    assert normalize_lang("zh-cn") == "zh-CN" and normalize_lang("pt-BR") == "pt"
    assert engine_lang("google", "zh-HK") == "zh-TW"
    assert engine_lang("argos", "zh-CN") == "zh"
    assert engine_lang("google", "") == "auto"


def test_detect_source():
    assert detect_source("The quick brown fox jumps over the lazy dog near the river", "abc(EN)") == "en"
    assert detect_source("Hi", "abc(EN)") == "en"            # curto → dica do alfabeto
    assert detect_source("なにかテキスト", "あ") == "ja"
    assert detect_source("Esta é uma frase bem comprida em português para testar", "abc(BR)") == "pt"


def test_clean_ocr_text():
    assert clean_ocr_text("你 好  世 界\n\n", "你") == "你好世界"
    assert clean_ocr_text("| am here\r\n  and   there ", "abc(EN)") == "I am here\nand there"
    assert clean_ocr_text("a | b", "abc(BR)") == "a | b"


def test_bbox():
    assert normalize_bbox((10, 20, 5, 2)) == (5, 2, 10, 20)
    assert normalize_bbox((0, 0, 2, 2)) is None
    assert normalize_bbox(None) is None
    assert normalize_bbox((-1920, 0, -10, 100)) == (-1920, 0, -10, 100)  # monitor à esquerda


def test_profile_roundtrip(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile(name="Meu Jogo: RPG", mode="dual", region_a=[10, 10, 200, 100], region_b=[300, 10, 500, 100],
                target="ja", alphabet="あ", interval=0.5)
    p.preprocess.scale = 3
    store.save(p)
    store.save_last(p)
    assert store.list() == ["Meu Jogo: RPG"]
    q = store.load("Meu Jogo: RPG")
    assert q.mode == "dual" and q.target == "ja" and q.preprocess.scale == 3
    assert q.channels() == {"a": (10, 10, 200, 100), "b": (300, 10, 500, 100)}
    assert store.load_last().name == "Meu Jogo: RPG"
    assert store.delete("Meu Jogo: RPG") and store.list() == []


def test_profile_sanitizes_and_accepts_v2_names():
    p = Profile.from_dict({"target": "Español", "alphabet": "???", "interval": 99,
                           "region_single": [5, 5, 5, 5], "mode": "x"})
    assert p.target == "es" and p.alphabet == "abc(EN)" and p.interval == 5.0
    assert p.region_single is None and p.mode == "single" and p.channels() == {}


def test_settings(tmp_path):
    f = tmp_path / "s.json"
    s = config.Settings(f)
    assert s.get("ai.enabled") is False and s.get("ui.language") == "auto"
    s.set("capture.interval", 99)
    s.set("ai.gemini_key", "dummy")
    s2 = config.Settings(f)
    assert s2.get("capture.interval") == 5.0 and s2.gemini_key() == "dummy"
    f.write_text("{not json")
    assert config.Settings(f).get("capture.interval") == 1.0


def test_gemini_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "envkey")
    assert config.Settings(tmp_path / "x.json").gemini_key() == "envkey"


def test_config_dir_override():
    assert str(paths.config_dir()).startswith(str(paths.config_dir()))


def test_smart_join_lines():
    from egt.languages import smart_join_lines
    assert smart_join_lines("Hello brave\nadventurer, welcome") == "Hello brave adventurer, welcome"
    assert smart_join_lines("Hi there.\nHow are you?") == "Hi there.\nHow are you?"
    assert smart_join_lines("你好\n世界", cjk=True) == "你好世界"
    assert smart_join_lines("\n\n") == ""


def test_profile_font_family_default_and_validation():
    assert Profile().font_family == "default"
    assert Profile.from_dict({}).font_family == "default"                       # perfis antigos (4.0.3): sem o campo
    assert Profile.from_dict({"font_family": "poppins"}).font_family == "poppins"
    for bad in ("x;}</style>", "A B", "", None, 123, "a" * 50):
        assert Profile.from_dict({"font_family": bad}).font_family in ("default", "123")   # nunca CSS arbitrário
    assert Profile.from_dict({"font_family": "x;}"}).font_family == "default"
    assert Profile.from_dict({"font_family": "pixel"}).to_dict()["font_family"] == "pixel"


def test_settings_language_auto_and_codes(tmp_path):
    f = tmp_path / "s.json"
    s = config.Settings(f)
    assert s.get("ui.language") == "auto"
    for good in ("auto", "pt-BR", "en", "ja", "zh-TW", "ar", "hi"):
        s.set("ui.language", good)
        assert config.Settings(f).get("ui.language") == good
    for bad in ("../x", "<script>", "", "english-us-long", 5, None):
        s.set("ui.language", bad)
        assert config.Settings(f).get("ui.language") == "auto"
