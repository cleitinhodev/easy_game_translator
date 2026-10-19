"""4.0.6: chaves cifradas em disco, migração, remoção com limpeza de restos, seleção única de IA, teste por provedor."""
import ctypes
import json
import logging
import sys

import pytest
from fastapi.testclient import TestClient

from egt import vault
from egt.config import MASK, SECRET_PATHS, Settings, apply_changes, public_view

KEY = "AI" "za" "SyD-teste_1234567890abcdefghijklmnop"   # formato de chave Google (falsa; partida p/ o scanner)


@pytest.fixture(autouse=True)
def _aes_only(monkeypatch):
    monkeypatch.setenv("EGT_VAULT_NO_KEYRING", "1")
    monkeypatch.delenv("EGT_VAULT_SCHEME", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def _grep(root, needle: str) -> list:
    hits = []
    for f in root.rglob("*"):
        if f.is_file():
            b = f.read_bytes()
            if needle.encode() in b or needle.encode("utf-16-le") in b:
                hits.append(f.name)
    return hits


# ------------------------------------------------------------------ DPAPI (ctypes) com um crypt32 falso
class _FakeDll:
    """Simula crypt32/kernel32: confere entropia + flag UI_FORBIDDEN e "cifra" com XOR presa à entropia."""
    calls: list = []
    _keep: list = []

    def __init__(self, name, use_last_error=False):
        self.name = name
        self.LocalFree = lambda p: _FakeDll.calls.append(("free", p))

    @staticmethod
    def _bytes(ref):
        b = ref._obj
        return ctypes.string_at(b.pbData, b.cbData)

    def _do(self, src, ent, flags, out, protect):
        data, entropy = self._bytes(src), self._bytes(ent)
        _FakeDll.calls.append(("protect" if protect else "unprotect", entropy, flags))
        if entropy != vault.ENTROPY:
            return 0
        if protect:
            res = b"DP" + bytes(c ^ 0x5A for c in data)
        else:
            if not data.startswith(b"DP"):
                return 0
            res = bytes(c ^ 0x5A for c in data[2:])
        buf = ctypes.create_string_buffer(res, len(res))
        _FakeDll._keep.append(buf)
        out._obj.cbData = len(res)
        out._obj.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
        return 1

    def CryptProtectData(self, src, desc, ent, r, p, flags, out):
        return self._do(src, ent, flags, out, True)

    def CryptUnprotectData(self, src, desc, ent, r, p, flags, out):
        return self._do(src, ent, flags, out, False)


def test_dpapi_wrapper_mocked(monkeypatch, tmp_path):
    monkeypatch.setattr(ctypes, "WinDLL", _FakeDll, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 13, raising=False)
    monkeypatch.setattr(vault.sys, "platform", "win32")
    _FakeDll.calls.clear()
    assert vault.scheme() == "dpapi"
    b = vault.protect(KEY, "ai.gemini_key", tmp_path)
    assert b["enc"].startswith("dpapi:v1:") and KEY not in json.dumps(b)
    assert vault.unprotect(b, tmp_path) == KEY
    ops = [c for c in _FakeDll.calls if c[0] in ("protect", "unprotect")]
    assert all(e == vault.ENTROPY and f & vault.CRYPTPROTECT_UI_FORBIDDEN for _, e, f in ops)
    assert any(c[0] == "free" for c in _FakeDll.calls)          # LocalFree do buffer do DPAPI
    with pytest.raises(vault.VaultError):                          # blob "de outro usuário" → falha limpa
        vault.unprotect({"enc": "dpapi:v1:" + "QUJD"}, tmp_path)
    with pytest.raises(vault.VaultError):
        vault.unprotect({"enc": "dpapi:v1:@@não-base64"}, tmp_path)


def test_dpapi_blob_on_linux_is_unreadable(tmp_path):
    with pytest.raises(vault.VaultError):
        vault.unprotect({"enc": "dpapi:v1:QUJD"}, tmp_path)


def test_aesgcm_roundtrip_tamper_and_foreign_machine(tmp_path, monkeypatch):
    b = vault.protect(KEY, "ai.gemini_key", tmp_path)
    assert b["enc"].startswith("aesgcm:v1:")
    assert vault.unprotect(b, tmp_path) == KEY
    assert (tmp_path / vault.SALT_NAME).exists()
    if sys.platform != "win32":
        assert (tmp_path / vault.SALT_NAME).stat().st_mode & 0o077 == 0
    raw = bytearray(vault.base64.b64decode(b["enc"].split(":", 2)[2]))
    raw[-1] ^= 1
    with pytest.raises(vault.VaultError):
        vault.unprotect({"enc": "aesgcm:v1:" + vault.base64.b64encode(bytes(raw)).decode()}, tmp_path)
    # "outro PC": machine-id diferente → não abre
    monkeypatch.setattr(vault, "_machine_id", lambda: b"outra-maquina")
    vault._key_cache.clear()
    with pytest.raises(vault.VaultError):
        vault.unprotect(b, tmp_path)


def test_selftest_line(tmp_path):
    out = vault.selftest(tmp_path)
    assert "roundtrip=True" in out and "tamper_rejected=True" in out and "foreign_rejected=True" in out


# ------------------------------------------------------------------ migração / disco sem texto puro
def test_migration_plaintext_to_encrypted(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"ai": {"enabled": True, "provider": "ollama", "gemini_key": KEY},
                             "translation": {"libre_key": "libre-segredo-123", "microsoft_key": "ms-segredo-4567"}}))
    (tmp_path / "settings.json.bak").write_text(KEY)          # sobra antiga com a chave
    s = Settings(f)
    assert s.get("ai.mode") == "ollama"                         # enabled+provider → mode
    assert s.gemini_key() == KEY and s.secret("translation.libre_key") == "libre-segredo-123"
    disk = f.read_text()
    assert vault.is_blob(json.loads(disk)["ai"]["gemini_key"])
    for secret in (KEY, "libre-segredo-123", "ms-segredo-4567"):
        assert _grep(tmp_path, secret) == []                    # nada em texto puro na pasta (nem .bak/.tmp)
    assert "enabled" not in json.loads(disk)["ai"] and "provider" not in json.loads(disk)["ai"]


@pytest.mark.parametrize("raw,mode", [({"enabled": False, "provider": "gemini"}, "off"),
                                      ({"enabled": True, "provider": "gemini"}, "gemini"),
                                      ({"enabled": True}, "gemini"), ({}, "off"), ({"mode": "ollama"}, "ollama"),
                                      ({"mode": "bogus"}, "off")])
def test_mode_migration(tmp_path, raw, mode):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"ai": raw}))
    assert Settings(f).get("ai.mode") == mode


def test_explicit_model_choice_kept(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"ai": {"gemini_model": "gemini-3.8-flash"}}))
    assert Settings(f).get("ai.gemini_model") == "gemini-3.8-flash"


def test_save_via_api_leaves_no_plaintext(tmp_path):
    s = Settings(tmp_path / "settings.json")
    apply_changes(s, {"ai.gemini_key": KEY, "translation.microsoft_key": "ms-segredo-4567"})
    assert s.gemini_key() == KEY
    assert _grep(tmp_path, KEY) == [] and _grep(tmp_path, "ms-segredo-4567") == []
    view = json.dumps(public_view(s), ensure_ascii=False)
    assert KEY not in view and MASK in view and "aesgcm:v1" not in view
    apply_changes(s, {"ai.gemini_key": MASK})                   # máscara não sobrescreve
    assert s.gemini_key() == KEY


def test_copied_config_does_not_work_elsewhere(tmp_path, monkeypatch):
    s = Settings(tmp_path / "settings.json")
    s.set_secret("ai.gemini_key", KEY)
    other = tmp_path / "outro_pc"
    other.mkdir()
    (other / "settings.json").write_text((tmp_path / "settings.json").read_text())   # copia sem o sal / outro PC
    s2 = Settings(other / "settings.json")
    assert s2.gemini_key() == "" and s2.secret_state("ai.gemini_key") == "unreadable"
    assert public_view(s2)["secrets"]["state"]["ai.gemini_key"] == "unreadable"
    assert public_view(s2)["ai"]["gemini_key"] == ""


# ------------------------------------------------------------------ logs nunca recebem chaves
def test_log_redaction():
    from egt.logsetup import RedactFilter, redact
    assert KEY not in redact(f"erro com {KEY} no texto")
    rec = logging.LogRecord("x", logging.ERROR, "f", 1, "falhou: %s", (f"https://x/?key={KEY}",), None)
    RedactFilter().filter(rec)
    assert KEY not in rec.getMessage()


# ------------------------------------------------------------------ API: remover chave, variável de ambiente, teste por provedor
from tests.test_api import H, TOKEN, ctrl  # noqa: E402,F401
from egt.server.app import create_app  # noqa: E402


@pytest.fixture()
def client(ctrl):  # noqa: F811
    with TestClient(create_app(ctrl, TOKEN), base_url="http://127.0.0.1") as c:
        yield c


def test_remove_key_wipes_everything(client, ctrl, tmp_path):  # noqa: F811
    s = ctrl.settings
    s.set_secret("ai.gemini_key", KEY)
    root = s.path.parent
    log = root / "egt.log"
    log.write_text(f"linha antiga com {KEY}\n", encoding="utf-8")
    (root / "notes.txt").write_text(f"k={KEY}", encoding="utf-8")
    (root / "settings.json.bak").write_text(json.dumps({"ai": {"gemini_key": KEY}}))
    (root / "settings.tmp").write_text(KEY)
    assert client.post("/api/secrets/remove", json={"path": "ai.gemini_key"}, headers=H).status_code == 409
    r = client.post("/api/secrets/remove", json={"path": "ai.gemini_key", "confirmed": True}, headers=H)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert KEY not in r.text and rep["had_key"] and rep["still_found"] == []
    assert s.get("ai.gemini_key") == "" and s.gemini_key() == ""
    assert _grep(root, KEY) == []
    assert not (root / "settings.json.bak").exists() and not (root / "settings.tmp").exists()
    assert public_view(s)["secrets"]["state"]["ai.gemini_key"] == "none"
    # depois dá para colar uma nova
    client.patch("/api/settings", json={"changes": {"ai.gemini_key": "AI" "zaNOVA_chave_0000000000000000000000"}}, headers=H)
    assert s.gemini_key().startswith("AI" "zaNOVA")


def test_remove_requires_token_and_known_path(client):
    assert client.post("/api/secrets/remove", json={"path": "ai.gemini_key", "confirmed": True}).status_code in (401, 403)
    assert client.post("/api/secrets/remove", json={"path": "ui.language", "confirmed": True}, headers=H).status_code == 404


def test_remove_other_secret(client, ctrl):  # noqa: F811
    ctrl.settings.set_secret("translation.libre_key", "libre-segredo-123")
    r = client.post("/api/secrets/remove", json={"path": "translation.libre_key", "confirmed": True}, headers=H)
    assert r.status_code == 200 and ctrl.settings.secret("translation.libre_key") == ""


def test_env_status_and_remove_mocked(client, monkeypatch):
    import egt.secret_wipe as sw
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    st = client.get("/api/secrets/env", headers=H).json()
    assert st["vars"][0]["name"] == "GEMINI_API_KEY" and st["vars"][0]["process"] and KEY not in json.dumps(st)
    assert client.post("/api/secrets/env/remove", json={"name": "GEMINI_API_KEY"}, headers=H).status_code == 409
    assert client.post("/api/secrets/env/remove", json={"name": "PATH", "confirmed": True}, headers=H).status_code == 404
    # registro do Windows simulado: só HKCU pode ser apagado; HKLM nunca é tocado
    calls = []

    class FakeKey:
        def __init__(self, hive, sub):
            self.hive, self.sub = hive, sub

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeWinreg:
        HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, KEY_SET_VALUE = "HKCU", "HKLM", 2
        store = {("HKCU", "GEMINI_API_KEY"): KEY, ("HKLM", "GOOGLE_API_KEY"): "x" * 20}

        @staticmethod
        def OpenKey(hive, sub, *a):
            calls.append(("open", hive, a))
            return FakeKey(hive, sub)

        @staticmethod
        def QueryValueEx(k, name):
            if (k.hive, name) in FakeWinreg.store:
                return FakeWinreg.store[(k.hive, name)], 1
            raise FileNotFoundError

        @staticmethod
        def DeleteValue(k, name):
            calls.append(("delete", k.hive, name))
            if (k.hive, name) not in FakeWinreg.store:
                raise FileNotFoundError
            del FakeWinreg.store[(k.hive, name)]

    monkeypatch.setitem(sys.modules, "winreg", FakeWinreg)
    monkeypatch.setattr(sw.sys, "platform", "win32")
    broadcasts = []
    monkeypatch.setattr(sw, "_broadcast_env_change", lambda: broadcasts.append(1))
    st = {v["name"]: v for v in sw.env_status()}
    assert st["GEMINI_API_KEY"]["user"] and st["GOOGLE_API_KEY"]["system"] and not st["GOOGLE_API_KEY"]["user"]
    res = sw.remove_user_env("GEMINI_API_KEY")
    assert res["removed_user"] and not res["system_level"] and broadcasts == [1]
    import os
    assert "GEMINI_API_KEY" not in os.environ
    res2 = sw.remove_user_env("GOOGLE_API_KEY")                  # só existe no sistema → não remove, avisa
    assert not res2["removed_user"] and res2["system_level"]
    assert all(c[1] == "HKCU" for c in calls if c[0] == "delete")
    assert not any(c[0] == "open" and c[1] == "HKLM" and c[2] for c in calls)   # HKLM só leitura


def test_ollama_selected_never_calls_gemini(ctrl, monkeypatch):  # noqa: F811
    from egt.translate import ai as aimod
    from egt.translate.manager import build_engines
    called = []
    monkeypatch.setattr(aimod.GeminiTranslate, "__init__", lambda self, *a, **k: called.append("gemini") or None)
    ctrl.settings.set_secret("ai.gemini_key", KEY)
    ctrl.settings.set("ai.mode", "ollama", save=False)
    ids = [e.id for e in build_engines(ctrl.settings)]
    assert "ollama" in ids[0] and not called and not any("gemini" in i for i in ids)
    ctrl.settings.set("ai.mode", "off", save=False)
    ids = [e.id for e in build_engines(ctrl.settings)]
    assert not called and not any(i.startswith(("ollama", "gemini")) for i in ids)
    ctrl.settings.set("ai.mode", "gemini", save=False)
    monkeypatch.undo()


def test_ai_test_per_provider_and_error_mapping(client, ctrl, monkeypatch):  # noqa: F811
    import requests
    from egt.translate import ai as aimod
    ctrl.settings.set_secret("ai.gemini_key", KEY)
    ctrl.settings.set("ai.mode", "off", save=False)
    seen = []

    class R:
        def __init__(self, code, js=None):
            self.status_code, self._js, self.headers, self.text = code, js or {}, {}, ""

        def json(self):
            return self._js

    def fake_post(url, *a, **k):
        seen.append(url)
        if "generativelanguage" in url:
            assert KEY not in url                                   # chave vai no cabeçalho, nunca na URL
            return R(fake_post.code, {"candidates": [{"content": {"parts": [{"text": "Olá"}]}}]})
        return R(200, {"response": "Olá do Ollama"})
    monkeypatch.setattr(requests, "post", fake_post)
    for code, expect in ((404, "model_unavailable"), (403, "bad_key"), (400, "bad_key"), (429, "rate_limit")):
        fake_post.code = code
        r = client.post("/api/ai/test", json={"provider": "gemini"}, headers=H).json()
        assert not r["ok"] and r["code"] == expect, (code, r)
        assert KEY not in json.dumps(r)
    r404 = None
    fake_post.code = 404
    r404 = client.post("/api/ai/test", json={"provider": "gemini"}, headers=H).json()
    assert "gemini-3.5-flash-lite" in r404["message"]
    fake_post.code = 200
    r = client.post("/api/ai/test", json={"provider": "gemini"}, headers=H).json()
    assert r["ok"] and r["message"] == "Olá"
    seen.clear()
    r = client.post("/api/ai/test", json={"provider": "ollama"}, headers=H).json()
    assert r["ok"] and all("generativelanguage" not in u for u in seen)       # testar Ollama não toca no Gemini
    assert ctrl.settings.get("ai.mode") == "off"                                 # testar não muda a seleção
    assert client.post("/api/ai/test", json={"provider": "gemini"}).status_code in (401, 403)
    assert client.post("/api/ai/test", json={"provider": "evil"}, headers=H).status_code == 422


def test_ai_test_unreadable_key_message(client, ctrl):  # noqa: F811
    ctrl.settings.set("ai.gemini_key", {"enc": "dpapi:v1:QUJD"}, save=False)
    r = client.post("/api/ai/test", json={"provider": "gemini"}, headers=H).json()
    assert r["code"] == "key_unreadable" and "Cole a chave novamente" in r["message"]


def test_ollama_status(client, monkeypatch):
    import requests

    class R:
        status_code = 200

        def json(self):
            return {"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.2"}]}
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    r = client.post("/api/ai/ollama/status", json={}, headers=H).json()
    assert r == {"server": True, "models": ["llama3.2", "qwen2.5:7b"]}

    def boom(*a, **k):
        raise requests.ConnectionError("x")
    monkeypatch.setattr(requests, "get", boom)
    assert client.post("/api/ai/ollama/status", json={}, headers=H).json()["server"] is False
    assert client.post("/api/ai/ollama/status", json={"url": "file:///etc/passwd"}, headers=H).json()["error"] == "url"


def test_migration_when_encryption_unavailable_keeps_key_usable(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise vault.VaultError("sem cofre")
    monkeypatch.setattr(vault, "protect", boom)
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"ai": {"gemini_key": KEY}}))
    s = Settings(f)
    assert s.gemini_key() == KEY                                # não perde a chave do usuário
    assert public_view(s)["ai"]["gemini_key"] == MASK and KEY not in json.dumps(public_view(s))


def test_key_not_in_history_export_profiles_or_bug_log(client, ctrl, tmp_path):  # noqa: F811
    ctrl.settings.set_secret("ai.gemini_key", KEY)
    ctrl.profiles.save(ctrl.profile)
    for fmt in ("txt", "csv", "json"):
        r = client.get(f"/api/history/export?fmt={fmt}", headers=H)
        assert KEY not in r.text
    assert _grep(ctrl.settings.path.parent, KEY) == []
    logging.getLogger("egt.test").error("falha com chave %s", KEY)      # nem por engano chega ao log/aba Reportar Erros
    from egt.logsetup import RedactFilter, ring
    ring.addFilter(RedactFilter())
    logging.getLogger().addHandler(ring)
    try:
        logging.getLogger("egt.test").error("de novo %s", KEY)
        assert all(KEY not in line for line in ring.lines)
    finally:
        logging.getLogger().removeHandler(ring)
    assert KEY not in client.get("/api/settings", headers=H).text
