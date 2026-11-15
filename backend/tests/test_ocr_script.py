"""4.1 beta: script de OCR do usuário (contrato v1 "kind": "ocr") — mesmas entradas/saídas dos motores embutidos,
canal único/duplo, miniatura feita pelo app, modos exclusivos, aprovação por SHA-256 e a API."""
import base64
import json
import os
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from egt import demo, ocr_script, userscript
from egt.app import AppController
from egt.config import Settings, apply_changes
from egt.db import Database
from egt.glossary import Glossary
from egt.ocr.base import OcrError, OcrResult
from egt.ocr_script import OcrScriptBackend, OcrScriptError, parse_ocr_output, run_ocr_script, sample_image
from egt.pipeline import SCRIPT_ENGINE, Pipeline, PipelineConfig
from egt.preprocess import PreprocessOptions, preprocess
from egt.profiles import ProfileStore
from egt.server.app import create_app
from egt.translate.base import TranslationResult
from egt.userscript import ScriptError

ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES = ROOT / "examples" / "scripts"
TOKEN = "t0k3n-de-teste"
H = {"x-egt-token": TOKEN}


def write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return p


# lê o tamanho do PNG e devolve "canal:LxA" + confiança fixa (sem bibliotecas)
SIZE_JSON = r"""import json, struct, sys
req = json.load(sys.stdin)
outs = []
for im in req["images"]:
    with open(im["path"], "rb") as f:
        h = f.read(24)
    w, ht = struct.unpack(">II", h[16:24])
    outs.append({"text": "%s %dx%d %s" % (im["channel"], w, ht, req["ocr_lang"]), "confidence": 0.9})
print(json.dumps({"outputs": outs}))
"""
# texto "lido" = nome do canal + texto fixo, em texto puro com '---' no canal duplo
PLAIN = r"""import json, sys
req = json.load(sys.stdin)
print("\n---\n".join("Hello from channel " + im["channel"] for im in req["images"]))
"""
DUMP = r"""import json, os, sys
req = json.load(sys.stdin)
for im in req["images"]:
    im["exists"] = os.path.isfile(im["path"]) and os.path.isfile(im["raw_path"])
    im["dir_mode"] = oct(os.stat(os.path.dirname(im["path"])).st_mode & 0o777)
print(json.dumps({"outputs": [json.dumps(req)] * len(req["images"])}))
"""


def items(chans, opts=None):
    opts = opts or PreprocessOptions()
    return [(c, sample_image(c), preprocess(sample_image(c), opts)) for c in chans]


# ------------------------------------------------------------------ saída
def test_parse_ocr_output_forms():
    assert parse_ocr_output('{"outputs": ["a"]}', 1) == ([("a", None)], "json")
    assert parse_ocr_output('{"outputs": [{"text": "a", "confidence": 87.5}, "b"]}', 2) == ([("a", 87.5), ("b", None)], "json")
    assert parse_ocr_output('{"outputs": ["a", "b"], "confidences": [0.5, null]}', 2) == ([("a", 50.0), ("b", None)], "json")
    assert parse_ocr_output('{"outputs": [{"text": "x", "confidence": 250}]}', 1)[0] == [("x", 100.0)]
    assert parse_ocr_output('{"outputs": [{"text": "x", "confidence": "alta"}]}', 1)[0] == [("x", None)]
    assert parse_ocr_output('{"outputs": "só"}', 1)[0] == [("só", None)]
    assert parse_ocr_output("linha 1\nlinha 2\n", 1) == ([("linha 1\nlinha 2", None)], "text")
    assert parse_ocr_output("A1\n---\nB1\n", 2) == ([("A1", None), ("B1", None)], "text")
    assert parse_ocr_output("A1\n---\n", 2)[0] == [("A1", None), ("", None)]
    # nada impresso = nenhum texto lido (igual a um motor embutido), não é erro
    assert parse_ocr_output("  \n", 1)[0] == [("", None)]
    assert parse_ocr_output("", 2)[0] == [("", None), ("", None)]
    assert parse_ocr_output('{"outputs": ["", ""]}', 2)[0] == [("", None), ("", None)]
    for raw, n, code in (('{"outputs": ["a"]}', 2, "count"), ("sem separador", 2, "count"),
                         ('{"error": "sem tesseract"}', 1, "script_error"), ('{"outputs": [1]}', 1, "bad_output"),
                         ('{"outputs": 5}', 1, "bad_output")):
        with pytest.raises(ScriptError) as e:
            parse_ocr_output(raw, n)
        assert e.value.code == code


# ------------------------------------------------------------------ entrada / execução
def test_payload_contract_single_and_dual(tmp_path):
    p = write(tmp_path, "dump.py", DUMP)
    opts = PreprocessOptions(scale=2.0)
    r = run_ocr_script(str(p), items(["uni"], opts), "abc(BR)", preprocess=opts.to_dict())
    d = json.loads(r.results[0].text)
    assert d["version"] == 1 and d["kind"] == "ocr" and d["mode"] == "single" and d["channels"] == ["uni"]
    assert d["alphabet"] == "abc(BR)" and d["ocr_lang"] == "por" and d["lang_hint"] == "pt" and d["cjk"] is False
    assert d["preprocess"]["scale"] == 2.0
    im = d["images"][0]
    assert im["channel"] == "uni" and im["exists"] is True
    raw = sample_image("uni")
    assert (im["raw_width"], im["raw_height"]) == raw.size
    assert im["width"] == raw.width * 2 + 2 * opts.pad and im["height"] == raw.height * 2 + 2 * opts.pad   # pré-processada
    assert im["path"].endswith("uni.png") and im["raw_path"].endswith("uni_raw.png") and "base64" not in im
    if os.name != "nt":
        assert im["dir_mode"] == "0o700"                                  # pasta temporária privada
    assert not os.path.exists(os.path.dirname(im["path"]))               # apagada depois da leitura
    r = run_ocr_script(str(p), items(["a", "b"]), "あ", "dual", ["a", "b"])
    d = json.loads(r.results[0].text)
    assert d["mode"] == "dual" and [i["channel"] for i in d["images"]] == ["a", "b"] and d["cjk"] is True
    assert d["ocr_lang"] == "jpn" and len(r.results) == 2


B64 = r"""import base64, json, struct, sys
req = json.load(sys.stdin)
outs = []
for im in req["images"]:
    png = base64.b64decode(im["base64"])
    raw = base64.b64decode(im["raw_base64"])
    w, h = struct.unpack(">II", png[16:24])
    outs.append("%s %s %d %d %d %d" % (png[:4] == b"\x89PNG", raw[:4] == b"\x89PNG", w, h, im["width"], im["height"]))
print(json.dumps({"outputs": outs}))
"""


def test_base64_option(tmp_path):
    p = write(tmp_path, "b64.py", B64)
    t = run_ocr_script(str(p), items(["uni"]), "abc(EN)", with_base64=True).results[0].text.split()
    assert t[:2] == ["True", "True"] and t[2:4] == t[4:6]
    p2 = write(tmp_path, "nob64.py", "import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps({'outputs':[str('base64' in r['images'][0])]}))")
    assert run_ocr_script(str(p2), items(["uni"]), "abc(EN)").results[0].text == "False"


def test_run_json_and_plain(tmp_path):
    p = write(tmp_path, "size.py", SIZE_JSON)
    r = run_ocr_script(str(p), items(["uni"]), "abc(EN)")
    assert r.format == "json" and r.results[0].text.startswith("uni ") and r.results[0].text.endswith(" eng")
    assert r.results[0].confidence == 90.0 and r.results[0].engine == "script"
    p2 = write(tmp_path, "plain.py", PLAIN)
    r = run_ocr_script(str(p2), items(["a", "b"]), "abc(EN)")
    assert r.format == "text" and [x.text for x in r.results] == ["Hello from channel a", "Hello from channel b"]
    assert all(x.confidence is None for x in r.results)


def test_errors_timeout_exit_size_count(tmp_path, monkeypatch):
    slow = write(tmp_path, "slow.py", "import time\ntime.sleep(30)\n")
    t0 = time.time()
    with pytest.raises(ScriptError) as e:
        run_ocr_script(str(slow), items(["uni"]), "abc(EN)", timeout=1.0)
    assert e.value.code == "timeout" and time.time() - t0 < 8
    bad = write(tmp_path, "bad.py", "import sys\nsys.stderr.write('tesseract sumiu\\n')\nsys.exit(2)\n")
    with pytest.raises(ScriptError) as e:
        run_ocr_script(str(bad), items(["uni"]), "abc(EN)")
    assert e.value.code == "exit" and "tesseract sumiu" in e.value.detail
    one = write(tmp_path, "one.py", "print('{\"outputs\": [\"só um\"]}')\n")
    with pytest.raises(ScriptError) as e:
        run_ocr_script(str(one), items(["a", "b"]), "abc(EN)")
    assert e.value.code == "count"
    monkeypatch.setattr(userscript, "MAX_OUTPUT", 1000)
    big = write(tmp_path, "big.py", "print('x' * 50000)\n")
    with pytest.raises(ScriptError) as e:
        run_ocr_script(str(big), items(["uni"]), "abc(EN)")
    assert e.value.code == "too_big"
    with pytest.raises(ScriptError) as e:
        run_ocr_script(str(tmp_path / "nao_existe.py"), items(["uni"]), "abc(EN)")
    assert e.value.code == "not_found"
    # nenhuma pasta temporária esquecida, mesmo com erro/tempo esgotado
    left = [n for n in os.listdir(tempfile.gettempdir()) if n.startswith(ocr_script.TMP_PREFIX)
            and time.time() - os.path.getmtime(os.path.join(tempfile.gettempdir(), n)) < 60]
    assert left == []


def test_env_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("EGT_TOKEN", "segredo-do-app")
    monkeypatch.setenv("GEMINI_API_KEY", "chave-secreta")
    p = write(tmp_path, "env.py", "import os, json, sys\njson.load(sys.stdin)\nprint(json.dumps({'outputs':[json.dumps(dict(os.environ))]}))")
    env = json.loads(run_ocr_script(str(p), items(["uni"]), "abc(EN)").results[0].text)
    assert "EGT_TOKEN" not in env and "GEMINI_API_KEY" not in env and "chave-secreta" not in json.dumps(env)


def test_sweep_temp_removes_only_old_app_dirs(tmp_path):
    old = tempfile.mkdtemp(prefix=ocr_script.TMP_PREFIX)
    open(os.path.join(old, "uni.png"), "wb").close()
    new = tempfile.mkdtemp(prefix=ocr_script.TMP_PREFIX)
    foreign = tempfile.mkdtemp(prefix=ocr_script.TMP_PREFIX)        # tem arquivo que não é PNG → não é nosso
    open(os.path.join(foreign, "notas.txt"), "w").close()
    for d in (old, foreign):
        os.utime(d, (time.time() - 7200, time.time() - 7200))
    ocr_script.sweep_temp()
    try:
        assert not os.path.exists(old) and os.path.exists(new) and os.path.exists(foreign)
    finally:
        shutil.rmtree(new, ignore_errors=True)
        shutil.rmtree(foreign, ignore_errors=True)


# ------------------------------------------------------------------ exemplos que vão no repositório
def test_example_basic_template_single_and_dual():
    r = run_ocr_script(str(EXAMPLES / "ocr_modelo_basico.py"), items(["uni"]), "abc(EN)")
    assert r.format == "json" and r.results[0].text.startswith("Canal único: imagem de") and r.results[0].confidence == 100.0
    r = run_ocr_script(str(EXAMPLES / "ocr_modelo_basico.py"), items(["a", "b"]), "abc(EN)", "dual")
    assert [x.text.split(":")[0] for x in r.results] == ["Canal A", "Canal B"]


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract não instalado")
def test_example_tesseract_reads_text():
    r = run_ocr_script(str(EXAMPLES / "ocr_tesseract.py"), items(["a", "b"]), "abc(EN)", "dual")
    assert "adventurer" in r.results[0].text and "gate is closed" in r.results[0].text
    assert "castle" in r.results[1].text and r.results[0].confidence and r.results[0].confidence > 60


def test_example_tesseract_missing_is_friendly(tmp_path, monkeypatch):
    src = (EXAMPLES / "ocr_tesseract.py").read_text(encoding="utf-8").replace(
        "def achar_tesseract():", "def achar_tesseract():\n    return None\n\n\ndef _original():")
    p = write(tmp_path, "t.py", src)
    with pytest.raises(ScriptError) as e:
        run_ocr_script(str(p), items(["uni"]), "abc(EN)")
    assert e.value.code == "script_error" and "Tesseract" in e.value.detail


def _has_rapid():
    import importlib.util as u
    return bool(u.find_spec("rapidocr_onnxruntime") or u.find_spec("rapidocr"))


@pytest.mark.skipif(not _has_rapid(), reason="RapidOCR não instalado")
def test_example_rapidocr_reads_text(tmp_path, monkeypatch):
    # roda com o mesmo Python dos testes (que tem o RapidOCR)
    monkeypatch.setattr(userscript, "_python_cmd", lambda: [sys.executable])
    r = run_ocr_script(str(EXAMPLES / "ocr_rapidocr.py"), items(["uni"]), "abc(EN)", timeout=90)
    assert "adventurer" in r.results[0].text.lower() and r.results[0].confidence > 60


# ------------------------------------------------------------------ pipeline (mesmo caminho dos motores embutidos)
class Screen:
    """Tela falsa: cada região mostra um texto; trocar o texto muda a imagem."""

    def __init__(self):
        self.text = {0: "Hello from A", 400: "Hello from B"}

    def grab(self, bbox):
        from PIL import ImageDraw
        img = Image.new("RGB", (300, 40), (28, 31, 68))
        ImageDraw.Draw(img).text((6, 12), self.text.get(bbox[0], "?"), fill=(240, 240, 240))
        return img


def run_pipe(p, kinds=("translation",), n=2, timeout=15):
    end, evs = time.time() + timeout, []
    while time.time() < end and sum(e.kind in kinds for e in evs) < n:
        evs += p.drain()
        time.sleep(0.05)
    time.sleep(0.2)
    return evs + p.drain()


class FakeScriptBackend:
    """recognize_channels como o OcrScriptBackend, mas sem processo: lê o 'texto' do tamanho/ordem."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def supports(self, a):
        return True

    def recognize_channels(self, items, alphabet, mode="", channels=None):
        self.calls.append(([c for c, _, _ in items], mode, list(channels or []), [pre.size for _, _, pre in items]))
        if self.fail:
            raise OcrScriptError(ScriptError("exit", "1 — quebrou"))
        return [OcrResult(f"Read text from {c}", 91.0, "script", 5.0) for c, _, _ in items]


def make_pipe(backend, screen, channels):
    trans = []
    p = Pipeline(screen.grab, lambda e: backend if e == SCRIPT_ENGINE else pytest.fail("motor embutido chamado"),
                 lambda text, src, tgt: trans.append(text) or TranslationResult(f"PT:{text}", engine="mymemory"))
    p.set_config(PipelineConfig(channels=channels, ocr_engine=SCRIPT_ENGINE, stable_ms=0, min_chars=1, interval=0.2,
                                detect_source=False))
    return p, trans


def test_pipeline_single_channel_preview_ocr_translation():
    be, scr = FakeScriptBackend(), Screen()
    p, trans = make_pipe(be, scr, {"uni": (0, 0, 300, 40)})
    p.translate_now()
    evs = run_pipe(p, n=1)
    p.stop(wait=True)
    prev = [e for e in evs if e.kind == "preview"]
    assert len(prev) == 1 and prev[0].channel == "uni" and prev[0].data["image"].startswith("data:image/jpeg;base64,")
    assert prev[0].data["width"] == 300 and prev[0].data["height"] == 40          # miniatura da captura ORIGINAL
    ocr = [e for e in evs if e.kind == "ocr"]
    assert ocr[0].data["text"] == "Read text from uni" and ocr[0].data["engine"] == "script" and ocr[0].data["confidence"] == 91.0
    tr = [e for e in evs if e.kind == "translation"]
    assert tr[0].data["translated"] == "PT:Read text from uni" and trans == ["Read text from uni"]
    assert be.calls[0][:3] == (["uni"], "single", ["uni"])
    assert be.calls[0][3][0] == (300 * 2 + 12, 40 * 2 + 12)                     # o script recebe a pré-processada


def test_pipeline_dual_channel_one_call_two_images_two_previews():
    be, scr = FakeScriptBackend(), Screen()
    p, trans = make_pipe(be, scr, {"a": (0, 0, 300, 40), "b": (400, 0, 700, 40)})
    p.translate_now()
    evs = run_pipe(p, n=2)
    p.stop(wait=True)
    assert be.calls[0][:3] == (["a", "b"], "dual", ["a", "b"]) and len(be.calls) == 1   # UMA execução, 2 imagens
    assert sorted(e.channel for e in evs if e.kind == "preview") == ["a", "b"]
    assert {e.channel: e.data["text"] for e in evs if e.kind == "ocr"} == {"a": "Read text from a", "b": "Read text from b"}
    assert {e.channel: e.data["translated"] for e in evs if e.kind == "translation"} == \
        {"a": "PT:Read text from a", "b": "PT:Read text from b"}


def test_pipeline_dual_only_changed_channel_gets_new_preview():
    be, scr = FakeScriptBackend(), Screen()
    p, _ = make_pipe(be, scr, {"a": (0, 0, 300, 40), "b": (400, 0, 700, 40)})
    p.start()
    evs = run_pipe(p, n=2)
    n_calls = len(be.calls)
    scr.text[400] = "Changed text in B"                  # só o canal B muda
    evs2 = run_pipe(p, kinds=("preview",), n=1, timeout=5)
    p.stop(wait=True)
    assert n_calls >= 1 and len(be.calls) > n_calls
    assert be.calls[-1][0] == ["a", "b"]                 # canal duplo: o script sempre recebe as 2 imagens
    assert [e.channel for e in evs2 if e.kind == "preview"] == ["b"]   # mas só B ganha miniatura nova
    assert all(e.channel == "b" for e in evs2 if e.kind in ("ocr",))
    assert evs


def test_pipeline_script_error_keeps_thumbnail_and_reports():
    be, scr = FakeScriptBackend(fail=True), Screen()
    p, trans = make_pipe(be, scr, {"uni": (0, 0, 300, 40)})
    p.translate_now()
    evs = run_pipe(p, kinds=("error",), n=1, timeout=8)
    p.stop(wait=True)
    assert [e.channel for e in evs if e.kind == "preview"] == ["uni"]
    err = [e for e in evs if e.kind == "error"]
    assert err and err[0].data["message"].startswith("Script OCR [exit]") and trans == []


def test_pipeline_low_confidence_and_empty_like_builtin():
    class Low(FakeScriptBackend):
        def recognize_channels(self, items, alphabet, mode="", channels=None):
            return [OcrResult("", None, "script"), OcrResult("Some faint text", 10.0, "script")]
    be, scr = Low(), Screen()
    p, trans = make_pipe(be, scr, {"a": (0, 0, 300, 40), "b": (400, 0, 700, 40)})
    p.start()
    evs = run_pipe(p, kinds=("ocr",), n=1, timeout=3)
    p.stop(wait=True)
    assert not [e for e in evs if e.kind == "ocr"] and trans == []              # vazio / confiança baixa → ignorado
    assert sorted(e.channel for e in evs if e.kind == "preview")[:2] == ["a", "b"]


def test_builtin_engines_untouched_by_script_path():
    class Builtin:
        def supports(self, a):
            return True

        def recognize(self, img, a):
            return OcrResult("Builtin read", 88.0, "tesseract", 3.0)
    calls = []
    p = Pipeline(Screen().grab, lambda e: calls.append(e) or Builtin(),
                 lambda t, s, g: TranslationResult("PT:" + t, engine="mymemory"))
    p.set_config(PipelineConfig(channels={"a": (0, 0, 300, 40), "b": (400, 0, 700, 40)}, ocr_engine="tesseract",
                                stable_ms=0, min_chars=1))
    p.translate_now()
    evs = run_pipe(p, n=2)
    p.stop(wait=True)
    assert set(calls) == {"tesseract"} and len(calls) == 2                      # um recognize por canal, como sempre
    assert sorted(e.channel for e in evs if e.kind == "preview") == ["a", "b"]
    assert {e.data["engine"] for e in evs if e.kind == "ocr"} == {"tesseract"}


# ------------------------------------------------------------------ controlador / configurações / exclusividade
@pytest.fixture()
def ctrl(tmp_path):
    c = AppController(settings=Settings(tmp_path / "settings.json"), db=Database(tmp_path / "db.sqlite"),
                      profiles=ProfileStore(tmp_path / "profiles"), glossary=Glossary(tmp_path / "gloss.json"))
    yield c
    c.pipeline.stop(wait=True)


def approve(ctrl, path, enable=True):
    ctrl.settings.set("ocr_script.path", str(path), save=False)
    ctrl.settings.set("ocr_script.sha256", userscript.sha256_file(path), save=False)
    ctrl.settings.set("ocr_script.enabled", enable)
    ctrl.sync()


def test_settings_defaults_migration_and_locks(tmp_path):
    f = tmp_path / "antigo.json"
    f.write_text(json.dumps({"script": {"enabled": False}, "ocr": {"engine": "tesseract"}}))
    s = Settings(f)
    assert s.section("ocr_script") == {"enabled": False, "path": "", "sha256": "", "timeout": 20.0, "send_base64": False}
    f.write_text(json.dumps({"ocr_script": "estragado", "script": 3}))
    s = Settings(f)
    assert s.get("ocr_script.timeout") == 20.0 and s.get("script.timeout") == 15.0
    f.write_text(json.dumps({"ocr_script": {"timeout": 9999, "enabled": "sim", "path": 5}}))
    s = Settings(f)
    assert s.get("ocr_script.timeout") == 120.0 and s.get("ocr_script.enabled") is False and s.get("ocr_script.path") == ""
    for k in ("ocr_script.path", "ocr_script.sha256"):
        with pytest.raises(KeyError):
            apply_changes(s, {k: "x"})
    assert apply_changes(s, {"ocr_script.timeout": 30.0, "ocr_script.send_base64": True}) == ["ocr_script.timeout", "ocr_script.send_base64"]


def test_controller_engine_switch_and_exclusive(ctrl, tmp_path):
    builtin = ctrl.profile.ocr_engine
    assert ctrl.build_config().ocr_engine == builtin
    with pytest.raises(ValueError):                         # sem script aprovado não dá para escolher "script"
        ctrl.update_profile(ocr_engine="script")
    p = write(tmp_path, "size.py", SIZE_JSON)
    approve(ctrl, p)
    assert ctrl.build_config().ocr_engine == SCRIPT_ENGINE and ctrl.metrics()["ocr_engine"] == "script"
    assert ctrl.ocr_provider("script") is ctrl.ocr_script
    assert ctrl.profile.ocr_engine == builtin               # o motor escolhido no perfil fica guardado
    ctrl.update_profile(ocr_engine="rapidocr")              # escolher um motor embutido desliga o script de OCR
    assert ctrl.settings.get("ocr_script.enabled") is False and ctrl.build_config().ocr_engine == "rapidocr"
    ctrl.update_profile(ocr_engine="script")
    assert ctrl.settings.get("ocr_script.enabled") is True and ctrl.profile.ocr_engine == "rapidocr"
    # independente do modo de tradução: script de tradução / IA continuam valendo
    ctrl.settings.set("ai.mode", "ollama")
    assert ctrl.settings.get("ocr_script.enabled") is True
    snap = ctrl.snapshot()
    assert snap["ocr_script"]["enabled"] and snap["ocr_script"]["name"] == "size.py"


def test_backend_hash_change_and_not_approved(ctrl, tmp_path):
    be = ctrl.ocr_script
    with pytest.raises(OcrScriptError) as e:
        be.recognize(sample_image("uni"), "abc(EN)")
    assert e.value.code == "no_script" and isinstance(e.value, OcrError)
    p = write(tmp_path, "size.py", SIZE_JSON)
    approve(ctrl, p)
    assert be.recognize(sample_image("uni"), "abc(EN)").text.startswith("uni 640x")
    p.write_text(SIZE_JSON + "\n# mudou\n", encoding="utf-8")
    os.utime(p, (time.time() + 5, time.time() + 5))
    with pytest.raises(OcrScriptError) as e:
        be.recognize(sample_image("uni"), "abc(EN)")
    assert e.value.code == "hash_changed" and str(e.value).startswith("Script OCR [hash_changed]")
    assert be.info()["changed"] is True


def test_translation_script_and_ocr_script_together(ctrl, tmp_path):
    """Script de OCR lê + script de tradução traduz (modos independentes), num ciclo real com a tela de demonstração."""
    demo.install(ctrl)
    p_ocr = write(tmp_path, "ocr.py", PLAIN)
    approve(ctrl, p_ocr)
    tr = write(tmp_path, "tr.py", "import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps({'outputs':['TR:'+t for t in r['inputs']]}))")
    ctrl.settings.set("script.path", str(tr), save=False)
    ctrl.settings.set("script.sha256", userscript.sha256_file(tr), save=False)
    ctrl.settings.set("script.enabled", True)
    ctrl.update_profile(mode="dual")
    ctrl.set_region("a", [100, 220, 760, 300])
    ctrl.set_region("b", [100, 340, 760, 420])
    ctrl.settings.set("filters.min_chars", 1)
    ctrl.sync()
    ctrl.translate_now()
    end, evs = time.time() + 20, []
    while time.time() < end and sum(e.kind == "translation" for e in evs) < 2:
        evs += ctrl.poll_events(timeout=0.2)
    got = {e.channel: e.data["translated"] for e in evs if e.kind == "translation"}
    assert got == {"a": "TR:Hello from channel a", "b": "TR:Hello from channel b"}
    assert sorted(e.channel for e in evs if e.kind == "preview") == ["a", "b"]


# ------------------------------------------------------------------ API
@pytest.fixture()
def client(ctrl):
    demo.install(ctrl)
    with TestClient(create_app(ctrl, TOKEN), base_url="http://127.0.0.1") as c:
        yield c


def test_api_inspect_approve_test_forget(client, ctrl, tmp_path):
    p = write(tmp_path, "meu_ocr.py", SIZE_JSON)
    info = client.post("/api/ocr-script/inspect", json={"path": str(p)}, headers=H).json()
    assert info["ok"] and info["sha256"] == userscript.sha256_file(p) and info["runtime"] == "Python"
    assert client.patch("/api/settings", json={"changes": {"ocr_script.path": str(p)}}, headers=H).status_code == 422
    assert client.post("/api/ocr-script/approve", json={"path": str(p), "sha256": info["sha256"]}, headers=H).status_code == 400
    bad = client.post("/api/ocr-script/approve", json={"path": str(p), "sha256": "0" * 64, "confirmed": True}, headers=H).json()
    assert not bad["ok"] and bad["code"] == "hash_changed"
    ok = client.post("/api/ocr-script/approve", json={"path": str(p), "sha256": info["sha256"], "confirmed": True}, headers=H).json()
    assert ok["ok"] and ok["ocr_script"]["enabled"] and ok["settings"]["ocr_script"]["enabled"]
    assert ok["settings"]["script"]["enabled"] is False                     # o script de tradução não é tocado
    assert client.get("/api/state", headers=H).json()["metrics"]["ocr_engine"] == "script"
    # teste com imagens de exemplo (canal único e duplo): miniatura + imagem recebida + texto
    t1 = client.post("/api/ocr-script/test", json={"mode": "single"}, headers=H).json()
    assert t1["ok"] and len(t1["images"]) == 1 and t1["images"][0]["channel"] == "uni"
    assert t1["images"][0]["thumb"].startswith("data:image/jpeg;base64,") and t1["images"][0]["processed"].startswith("data:image/png")
    assert t1["images"][0]["text"].startswith("uni ") and t1["images"][0]["confidence"] == 90.0
    assert t1["payload"]["images"][0]["path"].startswith(".../")            # caminho escondido na tela
    t2 = client.post("/api/ocr-script/test", json={"mode": "dual"}, headers=H).json()
    assert t2["ok"] and [i["channel"] for i in t2["images"]] == ["a", "b"] and all(i["thumb"] for i in t2["images"])
    # com a região de verdade (tela de demonstração)
    assert client.post("/api/ocr-script/test", json={"mode": "dual", "source": "capture"}, headers=H).status_code == 409
    client.post("/api/profile/region", json={"channel": "uni", "bbox": [100, 220, 760, 300]}, headers=H)
    t3 = client.post("/api/ocr-script/test", json={"mode": "single", "source": "capture"}, headers=H).json()
    assert t3["ok"] and t3["images"][0]["width"] == 660
    pv = client.post("/api/capture/preview", json={"read": True}, headers=H).json()     # prévia da aba OCR usa o script
    assert pv["text"].startswith("uni ") and pv["confidence"] == 90.0
    # escolher motor embutido pelo perfil desliga o script; escolher "script" liga de novo
    r = client.patch("/api/profile", json={"ocr_engine": "rapidocr"}, headers=H)
    assert r.status_code == 200 and ctrl.settings.get("ocr_script.enabled") is False
    assert client.patch("/api/profile", json={"ocr_engine": "script"}, headers=H).status_code == 200
    assert ctrl.settings.get("ocr_script.enabled") is True
    # arquivo mudou → teste bloqueado, mas as miniaturas aparecem
    p.write_text(SIZE_JSON + "#x\n", encoding="utf-8")
    os.utime(p, (time.time() + 9, time.time() + 9))
    t4 = client.post("/api/ocr-script/test", json={"mode": "dual"}, headers=H).json()
    assert not t4["ok"] and t4["code"] == "hash_changed" and len(t4["images"]) == 2 and t4["images"][0]["thumb"]
    assert client.get("/api/ocr-script", headers=H).json()["changed"] is True
    f = client.post("/api/ocr-script/forget", headers=H).json()
    assert f["ocr_script"]["path"] == "" and f["ocr_script"]["enabled"] is False
    assert client.patch("/api/profile", json={"ocr_engine": "script"}, headers=H).status_code == 422


def test_api_test_validation(client):
    assert client.post("/api/ocr-script/test", json={"mode": "triple"}, headers=H).status_code == 422
    r = client.post("/api/ocr-script/test", json={"mode": "single"}, headers=H).json()
    assert not r["ok"] and r["code"] == "no_script" and r["images"][0]["thumb"]
