"""4.0.9: modo Scripts (contrato v1), verificação automática dos tradutores ao abrir e a fila (MyMemory em 1º)."""
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from egt import demo, userscript
from egt.app import AppController
from egt.config import Settings, apply_changes
from egt.db import Database
from egt.glossary import Glossary
from egt.pipeline import Pipeline, PipelineConfig
from egt.profiles import ProfileStore
from egt.server.app import create_app
from egt.translate import TranslationCache, TranslationManager, build_engines
from egt.translate.base import TranslationError, TranslationResult, Translator
from egt.userscript import ScriptError, parse_output, run_script

ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES = ROOT / "examples" / "scripts"
PY = sys.executable
TOKEN = "t0k3n-de-teste"
H = {"x-egt-token": TOKEN}


def write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return p


ECHO_JSON = """import json, sys
req = json.load(sys.stdin)
print(json.dumps({"outputs": ["<" + req["target_lang"] + "> " + t.upper() for t in req["inputs"]],
                  }, ensure_ascii=False))
"""
PLAIN = """import json, sys
req = json.load(sys.stdin)
print("\\n---\\n".join("plain:" + t for t in req["inputs"]))
"""


# ------------------------------------------------------------------ contrato / saída
def test_parse_output_json_and_plain():
    assert parse_output('{"outputs": ["a"]}', 1) == (["a"], "json")
    assert parse_output('{"outputs": ["a", "b"]}', 2) == (["a", "b"], "json")
    assert parse_output("olá mundo\nsegunda linha\n", 1) == (["olá mundo\nsegunda linha"], "text")
    assert parse_output("A1\nA2\n---\nB1\n", 2) == (["A1\nA2", "B1"], "text")
    with pytest.raises(ScriptError) as e:
        parse_output('{"outputs": ["a"]}', 2)
    assert e.value.code == "count"
    with pytest.raises(ScriptError) as e:
        parse_output("sem separador", 2)
    assert e.value.code == "count"
    with pytest.raises(ScriptError) as e:
        parse_output('{"error": "cota esgotada"}', 1)
    assert e.value.code == "script_error" and "cota" in e.value.detail
    with pytest.raises(ScriptError) as e:
        parse_output('{"outputs": [1]}', 1)
    assert e.value.code == "bad_output"
    with pytest.raises(ScriptError) as e:
        parse_output("   \n", 1)
    assert e.value.code == "empty"


def test_run_single_and_dual_json(tmp_path):
    p = write(tmp_path, "t.py", ECHO_JSON)
    r = run_script(str(p), ["olá, ação"], "pt", "en")
    assert r.outputs == ["<en> OLÁ, AÇÃO"] and r.format == "json"
    r = run_script(str(p), ["one", "two"], "en", "pt")
    assert r.outputs == ["<pt> ONE", "<pt> TWO"]


def test_run_plain_single_and_dual(tmp_path):
    p = write(tmp_path, "plain.py", PLAIN)
    assert run_script(str(p), ["x"], "en", "pt").outputs == ["plain:x"]
    r = run_script(str(p), ["a", "b"], "en", "pt")
    assert r.outputs == ["plain:a", "plain:b"] and r.format == "text"


def test_payload_contract(tmp_path):
    p = write(tmp_path, "dump.py", "import sys, json\nd=json.load(sys.stdin)\nprint(json.dumps({'outputs':[json.dumps(d)]*len(d['inputs'])}))")
    d = json.loads(run_script(str(p), ["A", "B"], "", "ja").outputs[0])
    assert d == {"version": 1, "mode": "dual", "inputs": ["A", "B"], "source_lang": "auto", "target_lang": "ja",
                 "channels": ["a", "b"]}
    d = json.loads(run_script(str(p), ["só"], "en", "pt").outputs[0])
    assert d["mode"] == "single" and d["channels"] == ["uni"] and d["inputs"] == ["só"]


def test_timeout_kills(tmp_path):
    p = write(tmp_path, "slow.py", "import time\ntime.sleep(30)\n")
    t0 = time.time()
    with pytest.raises(ScriptError) as e:
        run_script(str(p), ["x"], "en", "pt", timeout=1.0)
    assert e.value.code == "timeout" and time.time() - t0 < 8


def test_exit_code_and_stderr(tmp_path):
    p = write(tmp_path, "bad.py", "import sys\nsys.stderr.write('deu ruim aqui\\n')\nsys.exit(3)\n")
    with pytest.raises(ScriptError) as e:
        run_script(str(p), ["x"], "en", "pt")
    assert e.value.code == "exit" and "3" in e.value.detail and "deu ruim" in e.value.detail
    assert e.value.user_message().startswith("Script [exit]")


def test_output_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(userscript, "MAX_OUTPUT", 1000)
    p = write(tmp_path, "big.py", "print('x' * 50000)\n")
    with pytest.raises(ScriptError) as e:
        run_script(str(p), ["x"], "en", "pt")
    assert e.value.code == "too_big"


def test_env_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("EGT_TOKEN", "segredo-do-app")
    monkeypatch.setenv("GEMINI_API_KEY", "chave-secreta")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123")
    p = write(tmp_path, "env.py", "import os, json\nprint(json.dumps({'outputs':[json.dumps(dict(os.environ))]}))")
    env = json.loads(run_script(str(p), ["x"], "en", "pt").outputs[0])
    for k in ("EGT_TOKEN", "GEMINI_API_KEY", "LD_LIBRARY_PATH"):
        assert k not in env
    assert "segredo-do-app" not in json.dumps(env) and "chave-secreta" not in json.dumps(env)
    assert env.get("EGT_SCRIPT_CONTRACT") == "1" and "PATH" in env


def test_no_shell_injection(tmp_path):
    p = write(tmp_path, "a b;touch PWNED.py", ECHO_JSON)          # nome estranho: vai como argumento, nunca por shell
    assert run_script(str(p), ["$(whoami) `id` ; rm -rf /"], "en", "pt").outputs == ["<pt> $(WHOAMI) `ID` ; RM -RF /"]
    assert not (tmp_path / "PWNED.py").exists()


def test_missing_runtime_and_unsupported(tmp_path, monkeypatch):
    p = write(tmp_path, "x.js", "console.log('oi')")
    monkeypatch.setattr(userscript, "_which", lambda n: None)
    with pytest.raises(ScriptError) as e:
        run_script(str(p), ["x"], "en", "pt")
    assert e.value.code == "no_runtime" and e.value.detail == "Node.js"
    q = tmp_path / "dados.xyz"
    q.write_text("?")
    q.chmod(0o644)
    with pytest.raises(ScriptError) as e:
        userscript.build_command(str(q))
    assert e.value.code == "unsupported"
    with pytest.raises(ScriptError) as e:
        run_script(str(tmp_path / "nao_existe.py"), ["x"])
    assert e.value.code == "not_found"


@pytest.mark.skipif(os.name == "nt", reason="sh/chmod")
def test_shell_script_and_executable(tmp_path):
    sh = write(tmp_path, "t.sh", "#!/bin/sh\ncat >/dev/null\necho 'saída do sh'\n")
    assert run_script(str(sh), ["x"]).outputs == ["saída do sh"]
    exe = write(tmp_path, "tradutor", "#!/bin/sh\ncat >/dev/null\necho '{\"outputs\": [\"a\", \"b\"]}'\n")
    assert run_script(str(exe), ["1", "2"]).outputs == ["a", "b"]


# ------------------------------------------------------------------ exemplos que vão no repositório
def test_example_template():
    r = run_script(str(EXAMPLES / "modelo_basico.py"), ["Hello", ""], "en", "pt")
    assert r.outputs == ["[pt] Hello", ""]


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js não instalado")
def test_example_offline_glossary_node():
    r = run_script(str(EXAMPLES / "glossario_offline.js"), ["The king awaits you in the throne room.", "Game Over"], "en", "pt")
    assert r.format == "text" and r.outputs == ["O rei espera por você na sala do trono.", "Fim de jogo"]
    assert run_script(str(EXAMPLES / "glossario_offline.js"), ["Mira: I will bring the healing potions."]).outputs == \
        ["Mira: Eu levo as poções de cura."]


def test_example_mymemory_reports_errors_nicely(tmp_path):
    # sem rede no teste: aponta a API para uma porta fechada e confere que vira {"error": ...} (mensagem amigável)
    src = (EXAMPLES / "mymemory_tradutor.py").read_text(encoding="utf-8").replace(
        'API = "https://api.mymemory.translated.net/get"', 'API = "http://127.0.0.1:9/get"')
    p = write(tmp_path, "mm.py", src)
    with pytest.raises(ScriptError) as e:
        run_script(str(p), ["Hello"], "en", "pt")
    assert e.value.code == "script_error" and "MyMemory" in e.value.detail
    assert run_script(str(p), [""], "en", "pt").outputs == [""]       # entrada vazia nem chama a rede


# ------------------------------------------------------------------ hash / aprovação / controlador
@pytest.fixture()
def ctrl(tmp_path):
    c = AppController(settings=Settings(tmp_path / "settings.json"), db=Database(tmp_path / "db.sqlite"),
                      profiles=ProfileStore(tmp_path / "profiles"), glossary=Glossary(tmp_path / "gloss.json"))
    yield c
    c.pipeline.stop(wait=True)


def approve(ctrl, path):
    ctrl.settings.set("script.path", str(path), save=False)
    ctrl.settings.set("script.sha256", userscript.sha256_file(path), save=False)
    ctrl.settings.set("script.enabled", True)


def test_script_mode_replaces_translators_and_hash_change(ctrl, tmp_path):
    called = []

    class Spy(Translator):
        id, name = "mymemory", "spy"

        def available(self):
            return True, ""

        def translate(self, text, src, tgt):
            called.append(text)
            return "via tradutor"

    ctrl.manager._engines = lambda: [Spy()]
    p = write(tmp_path, "t.py", ECHO_JSON)
    approve(ctrl, p)
    r = ctrl.translate_manual("hello world", "pt", "en")
    assert r.ok and r.text == "<pt> HELLO WORLD" and r.engine == "script" and called == []
    # o arquivo mudou → para e pede nova confirmação (nada roda)
    time.sleep(0.01)
    p.write_text(ECHO_JSON + "\n# mudou\n", encoding="utf-8")
    os.utime(p, (time.time() + 5, time.time() + 5))
    r = ctrl.translate_manual("hello world", "pt", "en")
    assert not r.ok and r.error.startswith("Script [hash_changed]") and called == []
    assert ctrl.script.info()["changed"] is True
    # script desligado → volta para a fila de tradutores
    ctrl.settings.set("script.enabled", False)
    assert ctrl.translate_manual("hello world", "pt", "en").text == "via tradutor"


def test_script_not_approved_or_missing(ctrl, tmp_path):
    ctrl.settings.set("script.enabled", True)
    r = ctrl.translate_manual("hi", "pt", "en")
    assert not r.ok and r.error.startswith("Script [no_script]")
    ctrl.settings.set("script.path", str(tmp_path / "sumiu.py"))
    assert ctrl.translate_manual("hi", "pt", "en").error.startswith("Script [not_found]")


def test_pipeline_dual_channel_calls_script_once_with_both():
    calls = []

    def batch(inputs, src, tgt, channels):
        calls.append((list(inputs), list(channels)))
        return [TranslationResult(f"T:{x}", engine="script") for x in inputs]

    from egt.ocr.base import OcrResult

    class Ocr:
        def recognize(self, img, alpha):
            return OcrResult(text="First channel text" if img.size[0] / img.size[1] < 10 else "Second channel text", confidence=95)

        def supports(self, a):
            return True

    from PIL import Image
    p = Pipeline(lambda bbox: Image.new("RGB", (300 if bbox[0] == 0 else 600, 40)), lambda e: Ocr(),
                 lambda *a: pytest.fail("translate_fn não deve ser chamada no modo Scripts"))
    p.emit_preview = False
    p.batch_fn, p.batch_active = batch, lambda: True
    p.set_config(PipelineConfig(channels={"a": (0, 0, 301, 40), "b": (400, 0, 702, 40)}, stable_ms=0, min_chars=1))
    p.translate_now()
    end, trs = time.time() + 10, []
    while time.time() < end and len(trs) < 2:
        trs += [e for e in p.drain() if e.kind == "translation"]
        time.sleep(0.05)
    p.stop(wait=True)
    assert {e.channel for e in trs} == {"a", "b"}
    assert all(e.data["ok"] and e.data["engine"] == "script" and e.data["translated"].startswith("T:") for e in trs)
    assert calls[-1][1] == ["a", "b"] and len(calls[-1][0]) == 2
    assert calls[-1][0] == ["First channel text", "Second channel text"]


# ------------------------------------------------------------------ API + modos exclusivos
@pytest.fixture()
def client(ctrl):
    demo.install(ctrl)
    with TestClient(create_app(ctrl, TOKEN), base_url="http://127.0.0.1") as c:
        yield c


def test_api_inspect_approve_test_forget(client, ctrl, tmp_path):
    p = write(tmp_path, "meu_tradutor.py", ECHO_JSON)
    info = client.post("/api/script/inspect", json={"path": str(p)}, headers=H).json()
    assert info["ok"] and info["sha256"] == userscript.sha256_file(p) and info["runtime"] == "Python" and info["runtime_found"]
    assert client.patch("/api/settings", json={"changes": {"script.path": str(p)}}, headers=H).status_code == 422
    assert client.patch("/api/settings", json={"changes": {"script.sha256": info["sha256"]}}, headers=H).status_code == 422
    assert client.post("/api/script/approve", json={"path": str(p), "sha256": info["sha256"]}, headers=H).status_code == 400
    bad = client.post("/api/script/approve", json={"path": str(p), "sha256": "0" * 64, "confirmed": True}, headers=H).json()
    assert not bad["ok"] and bad["code"] == "hash_changed"
    client.patch("/api/settings", json={"changes": {"ai.mode": "gemini"}}, headers=H)
    ok = client.post("/api/script/approve", json={"path": str(p), "sha256": info["sha256"], "confirmed": True}, headers=H).json()
    assert ok["ok"] and ok["script"]["enabled"] and ok["settings"]["ai"]["mode"] == "off"      # script ligado → IA desligada
    t1 = client.post("/api/script/test", json={"inputs": ["hello"], "tgt": "pt"}, headers=H).json()
    assert t1["ok"] and t1["outputs"] == ["<pt> HELLO"]
    t2 = client.post("/api/script/test", json={"inputs": ["a", "b"], "tgt": "pt"}, headers=H).json()
    assert t2["outputs"] == ["<pt> A", "<pt> B"]
    man = client.post("/api/translate/manual", json={"text": "hey", "tgt": "pt", "src": "en"}, headers=H).json()
    assert man["engine"] == "script" and man["text"] == "<pt> HEY"
    # IA ligada → script desligado (e vice-versa)
    s = client.patch("/api/settings", json={"changes": {"ai.mode": "ollama"}}, headers=H).json()["settings"]
    assert s["script"]["enabled"] is False and s["ai"]["mode"] == "ollama"
    s = client.patch("/api/settings", json={"changes": {"script.enabled": True}}, headers=H).json()["settings"]
    assert s["script"]["enabled"] is True and s["ai"]["mode"] == "off"
    p.write_text(ECHO_JSON + "#x\n", encoding="utf-8")
    os.utime(p, (time.time() + 9, time.time() + 9))
    t3 = client.post("/api/script/test", json={"inputs": ["x"]}, headers=H).json()
    assert not t3["ok"] and t3["code"] == "hash_changed"
    assert client.get("/api/script", headers=H).json()["changed"] is True
    f = client.post("/api/script/forget", headers=H).json()
    assert f["script"]["path"] == "" and f["script"]["enabled"] is False


def test_script_timeout_setting_clamped(ctrl):
    apply_changes(ctrl.settings, {"script.timeout": 999.0})
    ctrl.settings.save()
    assert ctrl.settings.get("script.timeout") == 120.0


# ------------------------------------------------------------------ fila de tradutores
class Fake(Translator):
    def __init__(self, eid, result=None, exc=None, ok=True):
        self.id, self.name, self.result, self.exc, self.ok, self.calls = eid, eid, result, exc, ok, 0

    def available(self):
        return (self.ok, "" if self.ok else "sem chave")

    def translate(self, text, src, tgt):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


def test_queue_first_working_delivers_and_others_not_called():
    a, b, c = Fake("mymemory", "um"), Fake("google", "dois"), Fake("bing", "três")
    m = TranslationManager(TranslationCache(Database()), lambda: [a, b, c])
    r = m.translate("Hello there friend", "en", "pt")
    assert r.text == "um" and r.engine == "mymemory" and (a.calls, b.calls, c.calls) == (1, 0, 0)
    a2, b2, c2 = Fake("mymemory", exc=TranslationError("caiu", "network")), Fake("google", "dois"), Fake("bing", "três")
    m2 = TranslationManager(TranslationCache(Database()), lambda: [a2, b2, c2])
    r = m2.translate("Hello there friend", "en", "pt")
    assert r.engine == "google" and (a2.calls, b2.calls, c2.calls) == (1, 1, 0)
    r = m2.translate("Another sentence here", "en", "pt")          # o que falhou fica em espera: nem é chamado
    assert r.engine == "google" and a2.calls == 1 and c2.calls == 0


def test_mymemory_first_by_default_and_migration(tmp_path):
    s = Settings(tmp_path / "novo.json")
    assert s.get("translation.order")[0] == "mymemory"
    assert [e.id for e in build_engines(s, "off")][0] == "mymemory"
    f = tmp_path / "antigo.json"
    f.write_text(json.dumps({"translation": {"order": ["google", "bing", "mymemory", "deepl", "argos"],
                                             "enabled": ["bing", "deepl"]}}))
    s = Settings(f)
    assert s.get("translation.order")[:5] == ["mymemory", "google", "bing", "deepl", "argos"]
    assert s.get("translation.enabled") == ["bing", "deepl"]                 # o que estava ligado não muda
    disk = json.loads(f.read_text())
    assert "mymemory_first" in disk["migrations"]
    # o usuário colocou o MyMemory em 3º depois da migração: não mexe de novo
    apply_changes(s, {"translation.order": ["google", "bing", "mymemory"]})
    assert Settings(f).get("translation.order")[:3] == ["google", "bing", "mymemory"]


# ------------------------------------------------------------------ verificação automática ao abrir
def test_autocheck_enables_passing_only(ctrl, monkeypatch):
    monkeypatch.delenv("EGT_NO_AUTOCHECK", raising=False)
    fakes = {"mymemory": Fake("mymemory", "Olá, aventureiro! O portão está fechado."),
             "google": Fake("google", exc=TranslationError("bloqueado", "blocked")),
             "yandex": Fake("yandex", "Olá, aventureiro! O portão está fechado."),
             "apertium": Fake("apertium", "Hello, adventurer! The gate is closed."),           # eco = falha
             "deepl": Fake("deepl", "x", ok=False)}                                            # sem chave: nem testa
    import egt.app as appmod
    monkeypatch.setattr(appmod, "engine_factories", lambda settings, timeout=None: {k: (lambda v=v: v) for k, v in fakes.items()})
    ctrl.settings.set("translation.enabled", ["google"])
    ctrl.settings.set("translation.order", ["mymemory", "google", "yandex", "apertium", "deepl"])
    seen = []
    st = ctrl.run_autocheck(on_update=lambda s: seen.append(s["state"]))
    assert st["state"] == "done" and st["total"] == 4
    assert sorted(st["passed"]) == ["mymemory", "yandex"] and sorted(st["failed"]) == ["apertium", "google"]
    assert st["activated"] == ["mymemory", "yandex"]
    assert ctrl.settings.get("translation.enabled") == ["mymemory", "google", "yandex"]   # na ordem da fila
    assert fakes["deepl"].calls == 0
    assert seen[0] == "running" and seen[-1] == "done"
    pr = ctrl.manager.probe_status()
    assert pr["mymemory"]["ok"] and not pr["google"]["ok"] and pr["mymemory"]["source"] == "auto"
    ctrl.manager.reset_backoff()                       # mudar configurações não apaga o resultado do teste
    assert ctrl.manager.probe_status()["yandex"]["ok"]


def test_autocheck_skips(ctrl, monkeypatch):
    monkeypatch.delenv("EGT_NO_AUTOCHECK", raising=False)
    ctrl.settings.set("translation.autocheck", False)
    assert ctrl.run_autocheck()["reason"] == "disabled"
    ctrl.settings.set("translation.autocheck", True)
    ctrl.settings.set("script.enabled", True)
    assert ctrl.run_autocheck()["reason"] == "script"
    monkeypatch.setenv("EGT_NO_AUTOCHECK", "1")
    assert ctrl.run_autocheck(force=True)["reason"] == "disabled_env"


def test_autocheck_parallel_and_bounded(ctrl, monkeypatch):
    monkeypatch.delenv("EGT_NO_AUTOCHECK", raising=False)

    class Slow(Fake):
        def translate(self, text, src, tgt):
            time.sleep(0.6)
            return "Olá, aventureiro!"

    fakes = {f"e{i}": Slow(f"e{i}") for i in range(6)}
    import egt.app as appmod
    monkeypatch.setattr(appmod, "engine_factories", lambda settings, timeout=None: {k: (lambda v=v: v) for k, v in fakes.items()})
    t0 = time.time()
    st = ctrl.run_autocheck()
    assert len(st["passed"]) == 6 and time.time() - t0 < 2.5          # em paralelo, não 6 × 0,6 s
