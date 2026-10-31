"""4.0.8: catálogo de tradutores, migração, segredos novos, eco, teste por motor e API."""
import json

import pytest
from fastapi.testclient import TestClient

from egt.config import MASK, SECRET_PATHS, Settings, apply_changes, public_view
from egt.db import Database
from egt.server.app import create_app
from egt.translate import TranslationCache, TranslationManager
from egt.translate.base import RateLimited, TranslationError, Translator
from egt.translate.manager import build_engines, is_echo
from tests.test_api import TOKEN, H, ctrl  # noqa: F401

NEW_SECRETS = {"translation.deepl_key": "deepl-segredo-0001:fx", "translation.gcloud_key": "AI" "zagcloud-segredo-0002",
               "translation.baidu_key": "baidu-segredo-0003", "translation.youdao_secret": "youdao-segredo-0004",
               "translation.niutrans_key": "niutrans-segredo-0005", "translation.mymemory_email": "eu@exemplo-segredo.com"}


def _grep(root, needle):
    return [p for p in root.rglob("*") if p.is_file() and needle.encode() in p.read_bytes()]


class Fake(Translator):
    def __init__(self, id_, fn):
        self.id, self.name, self.fn, self.calls = id_, id_, fn, 0

    def available(self):
        return True, "ok"

    def translate(self, text, src, tgt):
        self.calls += 1
        return self.fn(text, src, tgt)


# ------------------------------------------------------------------ eco
@pytest.mark.parametrize("src,out,expect", [
    ("The gate is closed", "The gate is closed", True), ("The gate is closed", "the gate is  closed", True),
    ("The gate is closed", "O portão está fechado", False), ("Nina", "Nina", False), ("OK", "OK", False),
    ("扉は閉まっている", "扉は閉まっている", True), ("12345", "12345", False)])
def test_is_echo(src, out, expect):
    assert is_echo(src, out, "en", "pt") is expect


def test_echo_is_never_cached_and_next_engine_used():
    cache = TranslationCache(Database())
    a = Fake("lingvaish", lambda t, s, g: t)
    b = Fake("good", lambda t, s, g: "O portão está fechado")
    mgr = TranslationManager(cache, lambda: [a, b])
    r = mgr.translate("The gate is closed", "en", "pt")
    assert r.ok and r.engine == "good" and r.codes["lingvaish"] == "echo"
    assert cache.get("The gate is closed", "en", "pt", "lingvaish") is None


def test_all_echo_returns_text_uncached():
    cache = TranslationCache(Database())
    a = Fake("a", lambda t, s, g: t)
    mgr = TranslationManager(cache, lambda: [a])
    r = mgr.translate("Já está em português aqui", "", "pt")
    assert r.ok and r.text == "Já está em português aqui" and cache.count() == 0


def test_lingva_cache_rows_purged():
    db = Database()
    c = TranslationCache(db)
    c.put("Hello there", "en", "pt", "lingva", "Hello there")
    c.put("Hello there", "en", "pt", "google", "Olá")
    TranslationCache(db)
    assert c.get("Hello there", "en", "pt", "lingva") is None and c.get("Hello there", "en", "pt", "google") == "Olá"


def test_error_codes_and_backoff_visible():
    def boom(t, s, g):
        raise TranslationError("chave inválida", "bad_key")
    mgr = TranslationManager(TranslationCache(Database()), lambda: [Fake("x", boom)])
    r = mgr.translate("Hello world", "en", "pt")
    assert not r.ok and r.codes == {"x": "bad_key"}
    st = mgr.engine_status()["x"]
    assert st["code"] == "bad_key" and st["cooldown"] >= 29


def test_test_engine_ignores_cooldown_and_reports():
    calls = []

    def fn(t, s, g):
        calls.append(t)
        if len(calls) == 1:
            raise RateLimited("429", retry_after=100)
        return "Olá"
    eng = Fake("y", fn)
    mgr = TranslationManager(TranslationCache(Database()), lambda: [eng])
    assert not mgr.translate("Hello", "en", "pt").ok
    assert mgr.engine_status()["y"]["cooldown"] > 50
    res = mgr.test_engine(eng, "Hello", "en", "pt")
    assert res["ok"] and res["text"] == "Olá" and mgr.engine_status()["y"]["cooldown"] == 0
    echo = mgr.test_engine(Fake("z", lambda t, s, g: t), "The gate is closed", "en", "pt")
    assert not echo["ok"] and echo["code"] == "echo"


# ------------------------------------------------------------------ configurações
def test_migration_lingva_to_mozhi_and_old_libre_default(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"translation": {"order": ["google", "mymemory", "libre", "lingva", "microsoft", "argos"],
                                             "enabled": ["google", "lingva", "mymemory"],
                                             "libre_url": "http://localhost:5000", "lingva_url": "https://lingva.ml"}}))
    s = Settings(f)
    assert s.get("translation.enabled") == ["google", "mozhi", "mymemory"]
    assert s.get("translation.order")[:4] == ["google", "mymemory", "libre", "mozhi"]
    assert s.get("translation.libre_url") == ""
    disk = json.loads(f.read_text())["translation"]
    assert "lingva_url" not in disk and "lingva" not in disk["enabled"]
    names = [e.id for e in build_engines(s, "off")]
    assert names == ["google", "mymemory", "mozhi"]


def test_custom_libre_server_kept(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"translation": {"libre_url": "http://localhost:5000", "enabled": ["libre"]}}))
    assert Settings(f).get("translation.libre_url") == "http://localhost:5000"


def test_new_defaults(tmp_path):
    s = Settings(tmp_path / "s.json")
    assert [e.id for e in build_engines(s, "off")] == ["google", "bing", "mymemory"]


def test_all_new_secrets_encrypted_masked_and_removable(tmp_path):
    s = Settings(tmp_path / "settings.json")
    for p in NEW_SECRETS:
        assert p in SECRET_PATHS
    apply_changes(s, dict(NEW_SECRETS))
    view = json.dumps(public_view(s), ensure_ascii=False)
    for p, v in NEW_SECRETS.items():
        assert s.secret(p) == v
        assert _grep(tmp_path, v) == [], p
        assert v not in view
        assert public_view(s)["secrets"]["state"][p] == "ok"
    assert MASK in view
    from egt.secret_wipe import remove_secret
    rep = remove_secret(s, "translation.deepl_key")
    assert rep["had_key"] and s.secret("translation.deepl_key") == ""
    assert s.secret("translation.baidu_key") == "baidu-segredo-0003"


def test_sanitize_bad_values(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"translation": {"mozhi_engine": "evil", "timeout": 999, "order": "x", "enabled": [1, "google"]}}))
    s = Settings(f)
    assert s.get("translation.mozhi_engine") == "duckduckgo" and s.get("translation.timeout") == 30.0
    assert s.get("translation.enabled") == ["google"] and isinstance(s.get("translation.order"), list)


# ------------------------------------------------------------------ API
@pytest.fixture()
def client(ctrl):  # noqa: F811
    with TestClient(create_app(ctrl, TOKEN), base_url="http://127.0.0.1") as c:
        yield c


def test_engines_endpoint_has_metadata_and_no_secrets(client, ctrl):  # noqa: F811
    ctrl.settings.set_secret("translation.deepl_key", "deepl-segredo-0001:fx")
    r = client.get("/api/translation/engines", headers=H)
    assert r.status_code == 200 and "deepl-segredo" not in r.text
    by = {e["id"]: e for e in r.json()}
    assert {"google", "bing", "mymemory", "mozhi", "yandex", "apertium", "libre", "deepl", "microsoft", "gcloud",
            "baidu", "youdao", "niutrans", "argos"} <= set(by)
    assert "lingva" not in by
    d = by["deepl"]["meta"]
    assert d["kind"] == "key" and d["key_url"].startswith("https://") and d["key_state"]["translation.deepl_key"] == "ok"
    assert by["deepl"]["available"] is True
    assert by["google"]["meta"]["official"] is False and by["mymemory"]["meta"]["official"] is True
    assert by["argos"]["meta"]["kind"] == "offline"


def test_engine_test_endpoint(client, ctrl, monkeypatch):  # noqa: F811
    import egt.app as appmod
    sent = []

    def fake_factories(settings):
        return {"google": lambda: Fake("google", lambda t, s, g: (sent.append((t, s, g)), "Olá, aventureiro!")[1]),
                "bing": lambda: Fake("bing", lambda t, s, g: (_ for _ in ()).throw(TranslationError("x", "network")))}
    monkeypatch.setattr(appmod, "engine_factories", fake_factories)
    r = client.post("/api/translation/engine_test", json={"engine": "google", "text": "Hello, adventurer!", "tgt": "pt"}, headers=H)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["text"] == "Olá, aventureiro!"
    assert sent == [("Hello, adventurer!", "", "pt")]
    r = client.post("/api/translation/engine_test", json={"engine": "bing", "text": "Hi there", "tgt": "pt"}, headers=H)
    assert r.json()["ok"] is False and r.json()["code"] == "network"
    r = client.post("/api/translation/engine_test", json={"engine": "nope", "text": "x"}, headers=H)
    assert r.json()["ok"] is False
    assert client.post("/api/translation/engine_test", json={"engine": "../x", "text": "x"}, headers=H).status_code == 422
    assert client.post("/api/translation/engine_test", json={"engine": "google", "text": "x"}).status_code == 401
    assert ctrl.cache.count() == 0      # teste não grava no cache


def test_engine_test_key_missing(client):
    r = client.post("/api/translation/engine_test", json={"engine": "deepl", "text": "Hello"}, headers=H)
    assert r.json()["ok"] is False and r.json()["code"] == "no_key"
    r = client.post("/api/translation/engine_test", json={"engine": "libre", "text": "Hello"}, headers=H)
    assert r.json()["ok"] is False and r.json()["code"] in ("config", "no_key")
