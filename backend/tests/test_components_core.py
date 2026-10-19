"""Gerenciador de componentes: lista de hosts oficiais, downloads (servidor local), pastas, remoção, detecção."""
import hashlib
import http.server
import importlib
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from egt.components import defs, sysinfo
from egt.components.base import Avail, ComponentError, Ctx, Detect, is_newer
from egt.components.download import DownloadManager, Expect, safe_filename, verify_file
from egt.components.net import AllowList, Http, HostNotAllowed, NetworkError, OFFICIAL_HOSTS
from egt.components.service import ComponentService
from egt.components.store import ComponentsStore, setup_environment, validate_dir

PAYLOAD = (b"EGT-test-payload-" * 4000)[:60_000]


class _H(http.server.BaseHTTPRequestHandler):
    slow = 0.0

    def log_message(self, *a):
        pass

    def do_GET(self):
        data = PAYLOAD
        start = 0
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            start = int(rng[6:].split("-")[0] or 0)
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(data) - start))
        self.end_headers()
        for i in range(start, len(data), 4000):
            try:
                self.wfile.write(data[i:i + 4000])
                self.wfile.flush()
            except OSError:
                return
            if _H.slow:
                time.sleep(_H.slow)


@pytest.fixture()
def srv():
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    _H.slow = 0.0
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


@pytest.fixture()
def store(tmp_path):
    st = ComponentsStore(tmp_path / "cfg" / "components.json")
    st.data["root"] = str(tmp_path / "comp")
    return st


@pytest.fixture()
def dm(tmp_path):
    events = []
    m = DownloadManager(Http(AllowList(allow_local=True)), lambda: tmp_path / "dl", emit=events.append, chunk=2000)
    m.events = events
    return m


# ------------------------------------------------------------------ registro
def test_registry_has_all_components_with_folders(store):
    ids = [c.id for c in defs.ALL]
    assert len(ids) == len(set(ids)) >= 13
    for must in ("python", "tesseract", "tessdata", "rapidocr", "easyocr", "paddleocr", "winocr", "opencv", "argos",
                 "ollama", "gemini", "gtts", "speechrecognition"):
        assert must in ids
    for cid in ids:
        assert store.dir_for(cid).is_absolute()


def test_service_rejects_unknown_component_id(store):
    svc = ComponentService(store)
    for bad in ("../etc", "nope", ""):
        with pytest.raises(KeyError):
            svc.comp(bad)
        with pytest.raises(KeyError):
            svc.install(bad, confirmed=True)


def test_official_hosts_are_only_known_projects():
    assert "pypi.org" in OFFICIAL_HOSTS and "ollama.com" in OFFICIAL_HOSTS
    assert not any(h.startswith("http") or "/" in h for h in OFFICIAL_HOSTS)
    for bad in ("example.com", "evil.pythonhosted.org.attacker.io", "pastebin.com", "bit.ly"):
        assert bad not in OFFICIAL_HOSTS


# ------------------------------------------------------------------ lista de permissão
def test_allowlist_blocks_unofficial_http_and_credentials():
    a = AllowList()
    assert a.check("https://pypi.org/pypi/six/json")
    for url in ("http://pypi.org/x", "https://evil.example.com/x", "https://pypi.org.evil.com/x",
                "https://user:pw@pypi.org/x", "ftp://pypi.org/x", "https://127.0.0.1/x", "file:///etc/passwd"):
        with pytest.raises(HostNotAllowed):
            a.check(url)
    assert AllowList(allow_local=True).check("http://127.0.0.1:9/x")


def test_http_never_contacts_disallowed_host():
    with pytest.raises(HostNotAllowed):
        Http().get_json("https://evil.example.com/a.json")


# ------------------------------------------------------------------ download
def test_download_progress_and_sha256_ok(dm, srv):
    exp = Expect(sha256=hashlib.sha256(PAYLOAD).hexdigest())
    _H.slow = 0.01
    j = dm.start("gtts", "", "x", f"{srv}/a.bin", "a.bin", exp)
    j = dm.wait(j.id, 20)
    assert j.state == "done" and j.verified == "sha256" and j.done == j.total == len(PAYLOAD)
    assert j.dest.read_bytes() == PAYLOAD
    prog = [e["data"]["done"] for e in dm.events if e["type"] == "component_job" and e["data"]["state"] == "running"]
    assert len(prog) >= 2 and prog == sorted(prog) and prog[-1] <= len(PAYLOAD)


def test_download_sha_mismatch_discards_file(dm, srv):
    j = dm.wait(dm.start("x", "", "x", f"{srv}/a.bin", "a.bin", Expect(sha256="0" * 64)).id, 20)
    assert j.state == "error" and "SHA256" in j.error
    assert not j.dest.exists() and not j.dest.with_name("a.bin.part").exists()


def test_download_git_sha1_verification(dm, srv):
    good = hashlib.sha1(b"blob %d\0" % len(PAYLOAD) + PAYLOAD).hexdigest()
    j = dm.wait(dm.start("x", "", "x", f"{srv}/b.bin", "b.bin", Expect(git_blob_sha1=good)).id, 20)
    assert j.state == "done" and j.verified == "git-sha1"
    j = dm.wait(dm.start("x", "y", "x", f"{srv}/c.bin", "c.bin", Expect(git_blob_sha1="ab" * 20)).id, 20)
    assert j.state == "error"


def test_download_cancel_keeps_part_and_resume_completes(dm, srv):
    _H.slow = 0.05
    j = dm.start("x", "", "x", f"{srv}/r.bin", "r.bin")
    t0 = time.time()
    while j.done < 8000 and time.time() - t0 < 10:
        time.sleep(0.02)
    assert dm.cancel(j.id)
    j = dm.wait(j.id, 10)
    assert j.state == "cancelled" and not j.dest.exists()
    part = j.dest.with_name("r.bin.part")
    assert part.exists() and 0 < part.stat().st_size < len(PAYLOAD)
    _H.slow = 0.0
    j2 = dm.wait(dm.start("x", "", "x", f"{srv}/r.bin", "r.bin", Expect(sha256=hashlib.sha256(PAYLOAD).hexdigest())).id, 20)
    assert j2.state == "done" and j2.dest.read_bytes() == PAYLOAD


def test_download_rejects_disallowed_host_before_any_job(tmp_path):
    m = DownloadManager(Http(AllowList()), lambda: tmp_path / "dl")
    with pytest.raises(HostNotAllowed):
        m.start("x", "", "x", "https://evil.example.com/a.exe", "a.exe")
    with pytest.raises(HostNotAllowed):
        m.start("x", "", "x", "http://pypi.org/a.exe", "a.exe")
    assert m.jobs == {}


def test_download_filename_cannot_escape_folder(dm, srv):
    for name in ("../../evil.txt", "..\\..\\evil.txt", "/etc/passwd", "a/b/../../c.bin"):
        j = dm.wait(dm.start("x", name, "x", f"{srv}/a.bin", name).id, 20)
        assert j.dest.parent == (dm._dir()).resolve() or j.dest.parent == dm._dir()
        assert ".." not in j.dest.name and "/" not in j.dest.name
    assert safe_filename("../../a b$.exe") == "a_b_.exe"


def test_one_active_job_per_item(dm, srv):
    _H.slow = 0.05
    a = dm.start("x", "i", "x", f"{srv}/a.bin", "a.bin")
    b = dm.start("x", "i", "x", f"{srv}/a.bin", "a.bin")
    assert a.id == b.id
    dm.cancel(a.id)


def test_download_post_step_runs_and_failure_is_reported(dm, srv):
    from egt.components.download import JobFailed
    ran = []
    j = dm.wait(dm.start("x", "p", "x", f"{srv}/a.bin", "p.bin", post=lambda job: ran.append(job.phase)).id, 20)
    assert j.state == "done" and ran == ["installing"]

    def boom(job):
        raise JobFailed("não deu", "faça assim")
    j = dm.wait(dm.start("x", "q", "x", f"{srv}/a.bin", "q.bin", post=boom).id, 20)
    assert j.state == "error" and j.error == "não deu" and j.remedy == "faça assim"


def test_task_job_progress_and_cancel(dm):
    def work(job):
        job.total = 10
        for _ in range(10):
            if job.cancel.is_set():
                return
            job.done += 1
            job.publish()
            time.sleep(0.01)
    j = dm.wait(dm.start_task("ollama", "m", "m", work).id, 10)
    assert j.state == "done" and j.done == 10


def test_verify_file_without_expectation_is_ok(tmp_path):
    f = tmp_path / "f"
    f.write_bytes(b"abc")
    assert verify_file(f, Expect()) == (True, "", "")


# ------------------------------------------------------------------ pastas / segurança de caminhos
def test_is_allowed_blocks_traversal_and_outside(store, tmp_path):
    store.ensure("tessdata")
    inside = store.tessdata_dir() / "por.traineddata"
    assert store.is_allowed(inside)
    assert store.is_allowed(store.root())
    assert not store.is_allowed(store.root() / ".." / "outside.txt")
    assert not store.is_allowed(store.tessdata_dir() / ".." / ".." / ".." / "etc")
    assert not store.is_allowed("/etc/passwd")
    assert not store.is_allowed(tmp_path)
    link = store.root() / "evil"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to("/etc")
        assert not store.is_allowed(link / "passwd")
    except OSError:
        pass


def test_validate_dir_rules(tmp_path):
    assert validate_dir(str(tmp_path / "ok"))["ok"]
    assert not validate_dir("relative/dir")["ok"]
    assert not validate_dir("")["ok"]
    assert not validate_dir("/")["ok"]
    assert not validate_dir("/a\x00b")["ok"]
    r = validate_dir(str(tmp_path / "ação"))
    assert r["ok"] and r["warnings"]
    assert not validate_dir(str(tmp_path / "x"), need_bytes=10 ** 18)["ok"]
    f = tmp_path / "file"
    f.write_text("x")
    assert not validate_dir(str(f / "sub"))["ok"]


def test_set_dir_copies_but_never_deletes_and_persists(store, tmp_path):
    old = store.ensure("tessdata")
    (old / "por.traineddata").write_bytes(b"1")
    new = tmp_path / "other" / "tess"
    r = store.set_dir("tessdata", str(new), copy_existing=True)
    assert r["ok"] and r["copied"] == 1 and (old / "por.traineddata").exists()
    assert (new / "por.traineddata").read_bytes() == b"1"
    again = ComponentsStore(store.file)
    assert again.dir_for("tessdata") == new
    assert store.set_dir("tessdata", "relative")["ok"] is False
    with pytest.raises(KeyError):
        store.set_dir("../x", str(tmp_path / "y"))
    store.reset_dir("tessdata")
    assert store.dir_for("tessdata") == store.root() / "tessdata"


def test_components_json_corrupt_falls_back(tmp_path):
    f = tmp_path / "components.json"
    f.write_text("{not json")
    s = ComponentsStore(f)
    assert s.root() == s.default_root()


def _clean_applied():
    from egt.components import store as store_mod
    old = store_mod._applied.get("sp")
    if old in sys.path:
        sys.path.remove(old)
    store_mod._applied["sp"] = None


def test_setup_environment_adds_site_packages_last_and_creates_dirs(store):
    _clean_applied()
    snapshot = list(sys.path)
    try:
        info = setup_environment(store)
        sp = str(store.site_packages())
        assert sys.path[-1] == sp and sys.path.count(sp) == 1
        assert sys.path[:len(snapshot)] == snapshot          # nada reordenado: o que já funciona continua primeiro
        for sub in ("site-packages", "downloads", "tessdata"):
            assert (store.root() / sub).is_dir()
        assert info["site_packages"] == sp
        setup_environment(store)
        assert sys.path.count(sp) == 1
        assert os.environ.get("EGT_EASYOCR_DIR")
        (store.site_packages() / "egt_probe_mod.py").write_text("VALUE = 42\n")
        assert importlib.import_module("egt_probe_mod").VALUE == 42
    finally:
        sys.path[:] = snapshot
        sys.modules.pop("egt_probe_mod", None)


def test_user_site_never_shadows_bundled_modules(store):
    snapshot = list(sys.path)
    try:
        (store.site_packages()).mkdir(parents=True, exist_ok=True)
        (store.site_packages() / "json.py").write_text("raise RuntimeError('shadow')\n")
        setup_environment(store)
        import json
        assert hasattr(json, "dumps")
    finally:
        sys.path[:] = snapshot


# ------------------------------------------------------------------ pip / remoção segura
def _fake_pkg(site: Path, name="fakepkg", ver="1.0", extra_record=""):
    (site / name).mkdir(parents=True, exist_ok=True)
    (site / name / "__init__.py").write_text("x=1")
    di = site / f"{name}-{ver}.dist-info"
    di.mkdir()
    (di / "METADATA").write_text(f"Name: {name}\nVersion: {ver}\n")
    (di / "RECORD").write_text(f"{name}/__init__.py,,\n{name}-{ver}.dist-info/METADATA,,\n{extra_record}")
    return di


def test_remove_pip_package_only_inside_site_dir(tmp_path):
    site = tmp_path / "sp"
    outside = tmp_path / "precious.txt"
    outside.write_text("keep")
    sibling = tmp_path / "sp2"
    sibling.mkdir()
    (sibling / "other.txt").write_text("keep")
    _fake_pkg(site, extra_record="../precious.txt,,\n../sp2/other.txt,,\n/etc/hostname,,\n")
    assert sysinfo.dist_in_dir(site, "fakepkg") == "1.0"
    n = sysinfo.remove_pip_package(site, "fakepkg")
    assert n >= 2
    assert outside.read_text() == "keep" and (sibling / "other.txt").exists() and os.path.exists("/etc/hostname")
    assert not (site / "fakepkg").exists() and sysinfo.dist_in_dir(site, "fakepkg") is None


def test_remove_pip_package_ignores_other_packages(tmp_path):
    site = tmp_path / "sp"
    _fake_pkg(site, "keepme")
    _fake_pkg(site, "dropme")
    sysinfo.remove_pip_package(site, "dropme")
    assert (site / "keepme" / "__init__.py").exists()


def test_tessdata_remove_only_named_user_file(store):
    d = store.ensure("tessdata")
    (d / "por.traineddata").write_bytes(b"1")
    (d / "jpn.traineddata").write_bytes(b"2")
    (store.root() / "keep.txt").write_text("k")
    ctx = Ctx(store, Http(AllowList()), lambda p, dflt=None: dflt, lambda: {})
    t = defs.TessdataComp()
    assert t.remove(ctx, "por") == {"removed": 1}
    assert not (d / "por.traineddata").exists() and (d / "jpn.traineddata").exists()
    for bad in ("../keep", "a/b", "", "por.traineddata\0"):
        with pytest.raises(ComponentError):
            t.remove(ctx, bad)
    assert (store.root() / "keep.txt").exists()


def test_pip_spec_validation_blocks_injection(tmp_path):
    py = sysinfo.PyInfo("/usr/bin/python3", "3.12.0", True)
    ok = sysinfo.pip_install_cmd(py, "gTTS", tmp_path)
    assert ok[-1] == "gTTS" and "--target" in ok and isinstance(ok, list)
    for bad in ("gtts; rm -rf /", "-r evil.txt", "--index-url http://evil", "a b", "../x", "git+https://x/y.git", ""):
        with pytest.raises(ValueError):
            sysinfo.pip_install_cmd(py, bad, tmp_path)
    assert "https://pypi.org/simple" in ok


def test_pick_wheel_prefers_pure_then_native():
    urls = [{"packagetype": "sdist", "filename": "a-1.tar.gz"},
            {"packagetype": "bdist_wheel", "filename": "a-1-cp312-cp312-win_amd64.whl", "url": "w"},
            {"packagetype": "bdist_wheel", "filename": "a-1-py3-none-any.whl", "url": "p"},
            {"packagetype": "bdist_wheel", "filename": "a-1-py3-none-any.whl", "url": "y", "yanked": True}]
    assert sysinfo.pick_wheel(urls, "cp312", "win_amd64")["url"] == "w"
    assert sysinfo.pick_wheel(urls[:1] + urls[2:3], "cp312", "win_amd64")["url"] == "p"
    assert sysinfo.pick_wheel(urls[:1], "cp312", "win_amd64") is None


def test_cross_flags_only_when_python_differs():
    mm = sysinfo.runtime_tuple()[:2]
    same = sysinfo.PyInfo("p", "%d.%d.1" % mm, True)
    other = sysinfo.PyInfo("p", "3.%d.1" % (mm[1] - 1), True)
    assert sysinfo.cross_flags(same) == []
    if sysinfo.platform_key():
        f = sysinfo.cross_flags(other)
        assert "--only-binary=:all:" in f and "--python-version" in f


def test_pick_pip_python_prefers_same_minor():
    mm = sysinfo.runtime_tuple()[:2]
    a = sysinfo.PyInfo("a", "3.9.1", True)
    b = sysinfo.PyInfo("b", "%d.%d.0" % mm, True)
    c = sysinfo.PyInfo("c", "%d.%d.0" % mm, False)
    assert sysinfo.pick_pip_python([a, c, b]).exe == "b"
    assert sysinfo.pick_pip_python([c]) is None
    assert sysinfo.pick_pip_python([]) is None


# ------------------------------------------------------------------ check_available com HTTP simulado
class FakeHttp(Http):
    def __init__(self, routes=None, offline=False):
        super().__init__(AllowList())
        self.routes, self.offline, self.calls = routes or {}, offline, []

    def _get(self, url):
        self.allow.check(url)
        self.calls.append(url)
        if self.offline:
            raise NetworkError("sem internet", offline=True)
        for k in sorted(self.routes, key=len, reverse=True):      # a rota mais específica ganha
            if k in url:
                v = self.routes[k]
                if isinstance(v, NetworkError):
                    raise v
                return v
        raise NetworkError("HTTP 404", status=404)

    def get_json(self, url, limit=0):
        return self._get(url)

    def get_text(self, url, limit=0):
        return self._get(url)

    def head(self, url):
        v = self._get(url)
        return {"content-length": str(v)} if isinstance(v, int) else {}

    def content_length(self, url):
        try:
            return int(self.head(url)["content-length"])
        except (NetworkError, KeyError):
            return None


def _ctx(store, http, plat="win32", frozen=False, usage=None, pythons=None):
    c = Ctx(store, http, lambda p, d=None: d, lambda: usage or {}, plat=plat, frozen=frozen)
    c._pythons = (lambda: pythons or [])
    return c


def test_pip_component_check_parses_pypi(store):
    wheel = {"packagetype": "bdist_wheel", "filename": "gTTS-2.5.4-py3-none-any.whl", "size": 28_000,
             "url": "https://files.pythonhosted.org/packages/x/gTTS-2.5.4-py3-none-any.whl",
             "digests": {"sha256": "ab" * 32}}
    ctx = _ctx(store, FakeHttp({"pypi.org/pypi/gTTS/json": {"info": {"version": "2.5.4"}, "urls": [wheel]}}))
    av = defs.GttsComp().check(ctx)
    assert av.ok and av.latest == "2.5.4" and av.size == 28_000 and av.expect.sha256 == "ab" * 32
    assert av.url.startswith("https://files.pythonhosted.org/")


def test_pip_component_check_no_binary_and_offline_and_rate_limit(store):
    sdist_only = {"info": {"version": "1"}, "urls": [{"packagetype": "sdist", "filename": "x.tar.gz"}]}
    av = defs.GttsComp().check(_ctx(store, FakeHttp({"pypi.org": sdist_only})))
    assert not av.ok and av.error == "no_binary"
    av = defs.GttsComp().check(_ctx(store, FakeHttp(offline=True)))
    assert not av.ok and av.offline and av.error == "offline"
    av = defs.GttsComp().check(_ctx(store, FakeHttp({"pypi.org": NetworkError("HTTP 429", status=429)})))
    assert av.error == "rate_limit" and not av.offline


def test_tessdata_check_reads_github_listing_with_git_sha(store):
    files = [{"name": "por.traineddata", "size": 1_982_756, "sha": "c" * 40,
              "download_url": "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/por.traineddata"},
             {"name": "README.md", "size": 1, "sha": "d" * 40}]
    av = defs.TessdataComp().check(_ctx(store, FakeHttp({"tessdata_fast/contents": files})))
    assert av.ok and av.items["por"]["size"] == 1_982_756 and av.items["por"]["expect"].git_blob_sha1 == "c" * 40
    assert "README" not in av.items


def test_python_check_picks_newest_with_installer_on_windows(store):
    http = FakeHttp({"python.org/ftp/python/": '<a href="3.12.1/">3.12.1/</a><a href="3.12.9/">3.12.9/</a>',
                     "python-3.12.9-amd64.exe": 25_000_000})
    av = defs.PythonComp().check(_ctx(store, http))
    assert av.ok and av.latest == "3.12.9" and av.size == 25_000_000 and av.url.startswith("https://www.python.org/")
    av = defs.PythonComp().check(_ctx(store, FakeHttp(), plat="linux"))
    assert not av.ok and av.note == "no_installer"
    assert defs.PythonComp().blocker(_ctx(store, FakeHttp(), plat="linux")) == "package_manager"


def test_tesseract_check_notes_no_hash(store):
    http = FakeHttp({"uni-mannheim": '<a href="tesseract-ocr-w64-setup-5.5.0.20241111.exe">x</a>',
                     "tesseract-ocr-w64-setup-5.5.0.20241111.exe": 48_000_000})
    av = defs.TesseractComp().check(_ctx(store, http))
    assert av.ok and av.note == "no_hash" and av.size == 48_000_000 and not av.expect.sha256


def test_version_compare():
    assert is_newer("3.12.10", "3.12.9") and not is_newer("1.0", "1.0") and not is_newer("", "1")


# ------------------------------------------------------------------ honestidade no app empacotado
def test_frozen_build_blocks_packages_it_cannot_load(store):
    ctx = _ctx(store, FakeHttp(), frozen=True, pythons=[sysinfo.PyInfo("p", "%d.%d.0" % sysinfo.runtime_tuple()[:2], True)])
    for c in (defs.EasyOcrComp(), defs.PaddleComp(), defs.ArgosComp()):
        assert c.blocker(ctx) == "frozen_unsupported", c.id
    assert defs.RapidOcrComp().blocker(ctx) == "builtin"      # já vem dentro do programa
    assert defs.GttsComp().blocker(ctx) == ""
    assert defs.WinOcrComp().blocker(_ctx(store, FakeHttp(), plat="linux")) == "not_windows"


def test_needs_python_when_no_pip_available(store):
    ctx = _ctx(store, FakeHttp(), pythons=[])
    assert defs.GttsComp().blocker(ctx) == "needs_python"


# ------------------------------------------------------------------ serviço: confirmar, instalar, instalador
def _svc(store, **kw):
    return ComponentService(store, http=kw.pop("http", FakeHttp()), **kw)


def test_install_and_remove_require_confirmation(store):
    svc = _svc(store)
    with pytest.raises(ComponentError) as e:
        svc.install("gtts")
    assert e.value.code == "confirm_required"
    with pytest.raises(ComponentError) as e:
        svc.remove("gtts")
    assert e.value.code == "confirm_required"
    with pytest.raises(ComponentError) as e:
        svc.run_installer("/x/y.exe")
    assert e.value.code == "confirm_required"


def test_run_installer_only_inside_downloads_and_exe(store):
    opened = []
    svc = _svc(store, startfile=opened.append)
    svc.ctx.plat = "win32"
    dl = store.downloads()
    dl.mkdir(parents=True, exist_ok=True)
    good = dl / "tess-setup.exe"
    good.write_bytes(b"MZ")
    txt = dl / "note.txt"
    txt.write_text("x")
    outside = store.root().parent / "evil.exe"
    outside.write_bytes(b"MZ")
    for bad in (str(outside), str(txt), str(dl / ".." / "evil.exe"), str(dl / "missing.exe"), "/bin/sh"):
        with pytest.raises(ComponentError) as e:
            svc.run_installer(bad, confirmed=True)
        assert e.value.code == "bad_path"
    assert opened == []
    assert svc.run_installer(str(good), confirmed=True) == {"ok": True} and opened == [str(good.resolve())]
    svc.ctx.plat = "linux"
    with pytest.raises(ComponentError) as e:
        svc.run_installer(str(good), confirmed=True)
    assert e.value.code == "not_windows"


def test_install_blocked_when_frozen_unsupported(store):
    svc = _svc(store)
    svc.ctx.frozen = True
    with pytest.raises(ComponentError) as e:
        svc.install("easyocr", confirmed=True)
    assert e.value.code == "frozen_unsupported"


def test_install_refuses_when_offline(store):
    py = sysinfo.PyInfo("p", "%d.%d.0" % sysinfo.runtime_tuple()[:2], True)
    svc = _svc(store, http=FakeHttp(offline=True), pythons=lambda: [py])
    with pytest.raises(ComponentError) as e:
        svc.install("gtts", confirmed=True)
    assert e.value.code == "offline"


def test_list_view_shape_and_summary_all_ok_when_nothing_needed(store):
    svc = _svc(store, usage=lambda: {"ocr_engine": "rapidocr", "alphabet": "abc(EN)"})
    v = svc.list_view()
    assert {c["id"] for c in v["components"]} == set(svc.registry)
    assert v["summary"]["all_ok"] is True and v["summary"]["needed"] == []
    assert all(c["status"] in ("ok", "update", "missing", "unavailable") for c in v["components"])
    assert all(c["primary"]["action"] in ("install", "update", "howto", "goto_ai", "none") for c in v["components"])
    tess = next(c for c in v["components"] if c["id"] == "tessdata")
    assert tess["needed"] is False


def test_missing_selected_ocr_engine_is_recommended(store, monkeypatch):
    monkeypatch.setattr(defs, "tesseract_exe", lambda ctx: None)
    svc = _svc(store, usage=lambda: {"ocr_engine": "tesseract", "alphabet": "abc(EN)"})
    v = svc.list_view()
    assert "tesseract" in v["summary"]["needed"] and v["summary"]["all_ok"] is False
    t = next(c for c in v["components"] if c["id"] == "tesseract")
    assert t["status"] == "missing"


def test_set_location_updates_environment_and_validates(store, tmp_path):
    snapshot = list(sys.path)
    try:
        svc = _svc(store)
        bad = svc.set_location("root", "relative/path")
        assert not bad["ok"] and store.data["root"] == str(tmp_path / "comp")
        new = tmp_path / "newroot"
        assert svc.set_location("root", str(new))["ok"]
        assert sys.path[-1] == str(new / "site-packages")
        with pytest.raises(KeyError):
            svc.set_location("nope", str(tmp_path / "z"))
    finally:
        sys.path[:] = snapshot


def test_folder_for_validates_and_creates(store):
    svc = _svc(store)
    p = svc.folder_for("tessdata")
    assert Path(p).is_dir() and store.is_allowed(p)
    with pytest.raises(KeyError):
        svc.folder_for("../../etc")


def test_service_events_flow_on_install_task(store):
    events = []
    svc = _svc(store, emit=events.append)
    done = []
    svc.on_changed = done.append
    j = svc.dm.start_task("ollama", "m", "m", lambda job: None)
    svc.dm.wait(j.id, 5)
    time.sleep(0.1)
    assert any(e["type"] == "component_changed" for e in events) and done == ["ollama"]


# ------------------------------------------------------------------ pip --target de verdade (um pacote minúsculo)
@pytest.mark.skipif(os.environ.get("EGT_SKIP_ONLINE") == "1", reason="sem internet")
def test_real_pip_target_install_and_remove(tmp_path):
    py = sysinfo.pick_pip_python()
    if py is None:
        pytest.skip("sem Python com pip")
    # só roda se o PyPI estiver acessível
    try:
        Http().get_json("https://pypi.org/pypi/six/json")
    except NetworkError:
        pytest.skip("PyPI inacessível")
    target = tmp_path / "sp"
    lines = []
    rc = sysinfo.run_streaming(sysinfo.pip_install_cmd(py, "six", target), lines.append, threading.Event(), timeout=180)
    assert rc == 0, "\n".join(lines[-5:])
    assert sysinfo.dist_in_dir(target, "six")
    assert sysinfo.remove_pip_package(target, "six") > 0
    assert sysinfo.dist_in_dir(target, "six") is None
