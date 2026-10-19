"""API REST + WebSocket do backend (TestClient) e pipeline ponta-a-ponta com OCR real e tradutor falso."""
import json
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from egt import demo, paths
from egt.app import AppController
from egt.config import Settings
from egt.db import Database
from egt.glossary import Glossary
from egt.profiles import ProfileStore
from egt.server.app import create_app

TOKEN = "t0k3n-de-teste"
H = {"x-egt-token": TOKEN}
WSH = {"host": "127.0.0.1"}


@pytest.fixture()
def ctrl(tmp_path):
    c = AppController(settings=Settings(tmp_path / "settings.json"), db=Database(tmp_path / "db.sqlite"),
                      profiles=ProfileStore(tmp_path / "profiles"), glossary=Glossary(tmp_path / "gloss.json"))
    demo.install(c)
    return c


@pytest.fixture()
def client(ctrl):
    with TestClient(create_app(ctrl, TOKEN), base_url="http://127.0.0.1") as c:
        yield c


def ws_url(token=TOKEN):
    return f"/ws?token={token}"


# ---------------------------------------------------------------- segurança
def test_rest_requires_token(client):
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/health", headers={"x-egt-token": "errado"}).status_code == 401
    assert client.get("/api/health", headers=H).json()["ok"] is True
    assert client.get(f"/api/health?token={TOKEN}").status_code == 200


def test_every_api_route_is_protected(client):
    for method, path in [("get", "/api/settings"), ("patch", "/api/profile"), ("post", "/api/pipeline/start"),
                         ("delete", "/api/cache"), ("get", "/api/history"), ("post", "/api/shutdown"),
                         ("get", "/api/logs"), ("post", "/api/tts"), ("post", "/api/stt")]:
        assert getattr(client, method)(path).status_code in (401, 422), path
        assert getattr(client, method)(path).status_code == 401, path


def test_host_header_guard_blocks_dns_rebinding(client):
    r = client.get("/api/health", headers={**H, "host": "evil.example.com"})
    assert r.status_code == 400


def test_cors_only_for_app_origins(client):
    ok = client.options("/api/health", headers={"origin": "egt://app", "access-control-request-method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "egt://app"
    bad = client.options("/api/health", headers={"origin": "https://evil.com", "access-control-request-method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_ws_rejects_bad_token_and_origin(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ws_url("nope"), headers=WSH):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ws_url(), headers={**WSH, "origin": "https://evil.com"}):
            pass


def test_secrets_are_masked_in_settings(client, ctrl):
    from egt.config import MASK, SECRET_PATHS
    for i, p in enumerate(SECRET_PATHS):
        ctrl.settings.set_secret(p, f"SEGREDO-{i}")
    body = client.get("/api/settings", headers=H).text
    assert "SEGREDO-" not in body and MASK in body
    assert '"enc"' not in body and "aesgcm:v1:" not in body       # nem o blob cifrado vai para a UI
    # reenviar a máscara não sobrescreve a chave real
    client.patch("/api/settings", json={"changes": {SECRET_PATHS[0]: MASK}}, headers=H)
    assert ctrl.settings.secret(SECRET_PATHS[0]) == "SEGREDO-0"


def test_settings_patch_validates(client):
    r = client.patch("/api/settings", json={"changes": {"nao.existe": 1}}, headers=H)
    assert r.status_code == 422
    r = client.patch("/api/settings", json={"changes": {"ui.language": "en"}}, headers=H)
    assert r.status_code == 200
    assert client.get("/api/settings", headers=H).json()["ui"]["language"] == "en"


# ---------------------------------------------------------------- perfil / regiões
def test_profile_and_region_roundtrip(client):
    r = client.post("/api/profile/region", json={"channel": "uni", "bbox": [10, 20, 400, 120]}, headers=H)
    assert r.status_code == 200 and r.json()["profile"]["region_single"] == [10, 20, 400, 120]
    assert client.post("/api/profile/region", json={"channel": "x", "bbox": [0, 0, 50, 50]}, headers=H).status_code == 422
    assert client.post("/api/profile/region", json={"channel": "uni", "bbox": [0, 0, 2, 2]}, headers=H).status_code == 422
    r = client.patch("/api/profile", json={"mode": "dual", "target": "en"}, headers=H)
    assert r.json()["profile"]["mode"] == "dual"
    assert client.patch("/api/profile", json={"interval": 99}, headers=H).status_code in (200, 422)


def test_profiles_save_load_delete(client):
    client.post("/api/profile/region", json={"channel": "uni", "bbox": [1, 2, 300, 100]}, headers=H)
    assert client.post("/api/profiles", json={"name": "Meu Jogo"}, headers=H).status_code == 200
    assert "Meu Jogo" in client.get("/api/profiles", headers=H).json()
    assert client.post("/api/profiles/load", json={"name": "Meu Jogo"}, headers=H).status_code == 200
    assert client.delete("/api/profiles?name=Meu%20Jogo", headers=H).status_code == 200
    assert "Meu Jogo" not in client.get("/api/profiles", headers=H).json()


def test_start_without_region_reports_error(client):
    r = client.post("/api/pipeline/start", headers=H).json()
    assert r["ok"] is False and r["running"] is False


# ---------------------------------------------------------------- tradução manual / cache / histórico
def test_manual_translation_cache_and_clear(client):
    r1 = client.post("/api/translate/manual", json={"text": "We must leave before the storm arrives.", "tgt": "pt"}, headers=H).json()
    assert r1["ok"] and "tempestade" in r1["text"] and r1["cached"] is False
    r2 = client.post("/api/translate/manual", json={"text": "We must leave before the storm arrives.", "tgt": "pt"}, headers=H).json()
    assert r2["cached"] is True
    assert client.get("/api/cache", headers=H).json()["count"] >= 1
    client.delete("/api/cache", headers=H)
    assert client.get("/api/cache", headers=H).json()["count"] == 0


def test_glossary_roundtrip(client):
    rules = {"rules": [{"find": "Hello", "replace": "Olá", "regex": False, "case": False, "word": True, "enabled": True}]}
    assert client.put("/api/glossary", json=rules, headers=H).status_code == 200
    got = client.get("/api/glossary", headers=H).json()
    assert got["rules"][0]["replace"] == "Olá"


# ---------------------------------------------------------------- pipeline ponta-a-ponta
def _collect(ws, pred, timeout=15.0):
    seen, end = [], time.time() + timeout
    while time.time() < end:
        m = ws.receive_json()
        seen.append(m)
        if pred(m):
            return seen
    return seen


def test_pipeline_end_to_end_ocr_translation_ws(client):
    pytest.importorskip("rapidocr_onnxruntime")
    assert client.patch("/api/profile", json={"ocr_engine": "rapidocr", "target": "pt"}, headers=H).status_code == 200
    client.post("/api/profile/region", json={"channel": "uni", "bbox": [100, 100, 760, 180]}, headers=H)
    with client.websocket_connect(ws_url(), headers=WSH) as ws:
        assert ws.receive_json()["type"] == "hello"
        r = client.post("/api/pipeline/start", headers=H).json()
        assert r["ok"] and r["running"]
        seen = _collect(ws, lambda m: m["type"] == "translation")
        client.post("/api/pipeline/stop", headers=H)
    types = [m["type"] for m in seen]
    assert "state" in types and "translation" in types
    tr = next(m for m in seen if m["type"] == "translation")
    assert tr["channel"] == "uni" and tr["data"]["ok"]
    assert tr["data"]["original"].lower().startswith(("the king", "take this", "we must", "careful", "you have"))
    assert tr["data"]["translated"] and not tr["data"]["translated"].startswith("[demo]")
    # histórico gravado e exportável
    hist = client.get("/api/history", headers=H).json()
    assert hist["count"] >= 1
    exp = client.get("/api/history/export?fmt=csv", headers=H).json()
    assert exp["count"] >= 1 and exp["filename"].endswith(".csv")
    m = client.get("/api/metrics", headers=H).json()
    assert "latency_ms" in m and "hit_rate" in m


def test_translate_now_single_shot(client):
    pytest.importorskip("rapidocr_onnxruntime")
    client.patch("/api/profile", json={"ocr_engine": "rapidocr"}, headers=H)
    client.post("/api/profile/region", json={"channel": "uni", "bbox": [0, 0, 760, 80]}, headers=H)
    with client.websocket_connect(ws_url(), headers=WSH) as ws:
        ws.receive_json()
        assert client.post("/api/pipeline/translate-now", headers=H).json()["ok"]
        seen = _collect(ws, lambda m: m["type"] == "translation")
    assert any(m["type"] == "translation" for m in seen)


def test_capture_preview_returns_png_data_url(client):
    r = client.post("/api/capture/preview", json={"bbox": [0, 0, 400, 100]}, headers=H)
    assert r.status_code == 200
    assert json.dumps(r.json()).count("data:image") >= 1


def test_about_and_logs(client):
    a = client.get("/api/about", headers=H).json()
    assert a["app"] and "modules" in a
    assert client.get("/api/logs", headers=H).status_code == 200


def test_ocr_engines_status_shape(client):
    r = client.get("/api/ocr/engines", headers=H).json()
    ids = {e["id"] for e in r}
    assert {"tesseract", "rapidocr"} <= ids
    for e in r:
        assert set(e) >= {"id", "name", "available", "detail", "pip_hint"}


# ---------------------------------------------------------------- reprocessamento imediato ao mudar configurações
def _run_and_get_first(client, ws):
    client.patch("/api/profile", json={"ocr_engine": "rapidocr", "target": "pt"}, headers=H)
    client.post("/api/profile/region", json={"channel": "uni", "bbox": [100, 100, 760, 180]}, headers=H)
    client.app.state.ctrl.grabber.period = 3600     # imagem estática durante o teste
    assert client.post("/api/pipeline/start", headers=H).json()["running"]
    return _collect(ws, lambda m: m["type"] == "translation")


def test_target_change_via_api_retranslates_static_capture(client):
    pytest.importorskip("rapidocr_onnxruntime")
    with client.websocket_connect(ws_url(), headers=WSH) as ws:
        ws.receive_json()
        first = [m for m in _run_and_get_first(client, ws) if m["type"] == "translation"][0]
        assert first["data"]["tgt"] == "pt"
        client.patch("/api/profile", json={"target": "en"}, headers=H)
        seen = _collect(ws, lambda m: m["type"] == "translation")
        client.post("/api/pipeline/stop", headers=H)
    assert any(m["type"] == "pending" for m in seen)
    tr = [m for m in seen if m["type"] == "translation"][-1]
    assert tr["data"]["tgt"] == "en" and tr["data"]["original"] == first["data"]["original"]


def test_glossary_profile_load_and_cache_only_trigger_refresh(client):
    pytest.importorskip("rapidocr_onnxruntime")
    with client.websocket_connect(ws_url(), headers=WSH) as ws:
        ws.receive_json()
        _run_and_get_first(client, ws)
        client.post("/api/profiles", json={"name": "P1"}, headers=H)
        client.put("/api/glossary", json={"rules": [], "keep": ["Nina"]}, headers=H)
        assert any(m["type"] == "translation" for m in _collect(ws, lambda m: m["type"] == "translation"))
        client.patch("/api/settings", json={"changes": {"translation.cache_only": True}}, headers=H)
        assert any(m["type"] == "translation" for m in _collect(ws, lambda m: m["type"] == "translation"))
        client.patch("/api/settings", json={"changes": {"translation.cache_only": False}}, headers=H)
        _collect(ws, lambda m: m["type"] == "translation")
        client.post("/api/profiles/load", json={"name": "P1"}, headers=H)
        assert any(m["type"] == "translation" for m in _collect(ws, lambda m: m["type"] == "translation"))
        client.post("/api/pipeline/stop", headers=H)


def test_profile_font_family_patch(client):
    r = client.patch("/api/profile", json={"font_family": "orbitron"}, headers=H)
    assert r.status_code == 200 and r.json()["profile"]["font_family"] == "orbitron"
    assert client.get("/api/profile", headers=H).json()["font_family"] == "orbitron"
    r = client.patch("/api/profile", json={"font_family": "bad;}value"}, headers=H)
    assert r.json()["profile"]["font_family"] == "default"
    assert client.get("/api/profile", headers=H).json()["font_family"] == "default"


def test_settings_language_codes_api(client):
    for code in ("auto", "ja", "zh-CN", "ar"):
        client.patch("/api/settings", json={"changes": {"ui.language": code}}, headers=H)
        assert client.get("/api/settings", headers=H).json()["ui"]["language"] == code
    client.patch("/api/settings", json={"changes": {"ui.language": "../../etc"}}, headers=H)
    assert client.get("/api/settings", headers=H).json()["ui"]["language"] == "auto"
