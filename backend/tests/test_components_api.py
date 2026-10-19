"""API /api/components (demonstração: nada vai para a internet de verdade)."""
import sys
import time

import pytest
from fastapi.testclient import TestClient

from egt import demo
from egt.app import AppController
from egt.components.store import ComponentsStore, set_store
from egt.config import Settings
from egt.db import Database
from egt.glossary import Glossary
from egt.profiles import ProfileStore
from egt.server.app import create_app

TOKEN = "t0k3n-de-teste"
H = {"x-egt-token": TOKEN}


@pytest.fixture()
def client(tmp_path):
    st = ComponentsStore(tmp_path / "components.json")
    st.data["root"] = str(tmp_path / "comp")
    set_store(st)
    c = AppController(settings=Settings(tmp_path / "settings.json"), db=Database(tmp_path / "db.sqlite"),
                      profiles=ProfileStore(tmp_path / "profiles"), glossary=Glossary(tmp_path / "gloss.json"))
    demo.install(c)
    try:
        with TestClient(create_app(c, TOKEN), base_url="http://127.0.0.1") as cl:
            cl.store = st
            yield cl
    finally:
        set_store(None)
        from egt.components import store as store_mod
        old = store_mod._applied.get("sp")
        if old in sys.path:
            sys.path.remove(old)
        store_mod._applied["sp"] = None


def test_every_components_route_requires_token(client):
    routes = [("get", "/api/components"), ("get", "/api/components/paths"), ("get", "/api/components/jobs"),
              ("post", "/api/components/check"), ("post", "/api/components/rescan"),
              ("post", "/api/components/gtts/check"), ("post", "/api/components/gtts/install"),
              ("post", "/api/components/gtts/remove"), ("post", "/api/components/gtts/folder"),
              ("post", "/api/components/gtts/rescan"), ("post", "/api/components/jobs/x/cancel"),
              ("post", "/api/components/run-installer"), ("post", "/api/components/location"),
              ("post", "/api/components/validate-dir"), ("post", "/api/components/_demo")]
    for m, p in routes:
        assert getattr(client, m)(p).status_code == 401, p
        assert getattr(client, m)(p, headers={"x-egt-token": "errado"}).status_code == 401, p


def test_list_has_summary_and_all_components(client):
    r = client.get("/api/components", headers=H).json()
    ids = {c["id"] for c in r["components"]}
    assert {"python", "tesseract", "tessdata", "rapidocr", "easyocr", "argos", "ollama", "gemini", "gtts"} <= ids
    assert "all_ok" in r["summary"] and r["demo"] is True
    assert r["paths"]["root"].endswith("comp")


def test_install_without_confirmation_is_refused(client):
    r = client.post("/api/components/gtts/install", json={}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "confirm_required"
    r = client.post("/api/components/gtts/remove", json={"confirmed": False}, headers=H)
    assert r.status_code == 409


def test_unknown_component_and_bad_item_are_rejected(client):
    assert client.post("/api/components/..%2Fetc/folder", headers=H).status_code in (404, 405)
    assert client.post("/api/components/nope/install", json={"confirmed": True}, headers=H).status_code == 404
    assert client.post("/api/components/nope/folder", headers=H).status_code == 404
    r = client.post("/api/components/tessdata/install", json={"item": "../../evil", "confirmed": True}, headers=H)
    assert r.status_code in (409, 422)


def test_check_then_install_tessdata_end_to_end_with_progress(client):
    c = client.post("/api/components/tessdata/check", json={}, headers=H).json()
    por = next(i for i in c["items"] if i["id"] == "por")
    assert por["size"] and not por["installed"]
    j = client.post("/api/components/tessdata/install", json={"item": "por", "confirmed": True}, headers=H).json()
    assert j["state"] in ("queued", "running") and j["component"] == "tessdata"
    t0 = time.time()
    while time.time() - t0 < 30:
        jobs = client.get("/api/components/jobs", headers=H).json()
        cur = next(x for x in jobs if x["id"] == j["id"])
        if cur["state"] in ("done", "error"):
            break
        time.sleep(0.2)
    assert cur["state"] == "done" and cur["verified"] == "git-sha1", cur
    f = client.store.tessdata_dir() / "por.traineddata"
    assert f.is_file() and f.stat().st_size == cur["total"]
    v = client.get("/api/components", headers=H).json()
    t = next(c for c in v["components"] if c["id"] == "tessdata")
    assert next(i for i in t["items"] if i["id"] == "por")["installed"]
    # remover (confirmado) só apaga o arquivo do idioma na pasta do usuário
    assert client.post("/api/components/tessdata/remove", json={"item": "por", "confirmed": True}, headers=H).status_code == 200
    assert not f.exists()


def test_folder_endpoint_returns_allowed_dir_and_creates_it(client):
    p = client.post("/api/components/tessdata/folder", headers=H).json()["path"]
    import os
    assert os.path.isdir(p) and client.store.is_allowed(p)


def test_root_folder_endpoint(client):
    import os
    p = client.post("/api/components/root/folder", headers=H).json()["path"]
    assert os.path.isdir(p) and p == str(client.store.root())


def test_location_validation(client, tmp_path):
    r = client.post("/api/components/location", json={"id": "tessdata", "path": "relativo"}, headers=H).json()
    assert r["ok"] is False and r["errors"]
    new = tmp_path / "minha pasta"
    r = client.post("/api/components/location", json={"id": "tessdata", "path": str(new)}, headers=H).json()
    assert r["ok"] and client.store.tessdata_dir() == new
    assert client.post("/api/components/location", json={"id": "nope", "path": str(new)}, headers=H).status_code == 404
    v = client.post("/api/components/validate-dir", json={"path": "/"}, headers=H).json()
    assert v["ok"] is False


def test_run_installer_rejects_unconfirmed_and_outside_paths(client):
    assert client.post("/api/components/run-installer", json={"path": "/bin/sh"}, headers=H).status_code == 409
    r = client.post("/api/components/run-installer", json={"path": "/bin/sh", "confirmed": True}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] in ("bad_path", "not_windows")


def test_offline_demo_gives_friendly_state_and_refuses_install(client):
    client.post("/api/components/_demo", json={"offline": True}, headers=H)
    v = client.post("/api/components/check", headers=H).json()
    assert any(c["offline"] for c in v["components"])
    r = client.post("/api/components/tessdata/install", json={"item": "por", "confirmed": True}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "offline"
    client.post("/api/components/_demo", json={"offline": False}, headers=H)


def test_demo_endpoint_not_available_outside_demo(tmp_path):
    st = ComponentsStore(tmp_path / "c.json")
    st.data["root"] = str(tmp_path / "comp")
    set_store(st)
    try:
        c = AppController(settings=Settings(tmp_path / "s.json"), db=Database(tmp_path / "d.sqlite"),
                          profiles=ProfileStore(tmp_path / "p"), glossary=Glossary(tmp_path / "g.json"))
        with TestClient(create_app(c, TOKEN), base_url="http://127.0.0.1") as cl:
            assert cl.post("/api/components/_demo", json={"offline": True}, headers=H).status_code == 404
            assert cl.get("/api/components", headers=H).status_code == 200
    finally:
        set_store(None)


def test_websocket_receives_job_events(client):
    with client.websocket_connect(f"/ws?token={TOKEN}", headers={"host": "127.0.0.1"}) as ws:
        assert ws.receive_json()["type"] == "hello"
        client.post("/api/components/tessdata/check", json={}, headers=H)
        client.post("/api/components/tessdata/install", json={"item": "jpn", "confirmed": True}, headers=H)
        seen = []
        t0 = time.time()
        while time.time() - t0 < 30:
            m = ws.receive_json()
            seen.append(m["type"])
            if m["type"] == "component_changed":
                break
    assert "component_job" in seen and "component_changed" in seen
