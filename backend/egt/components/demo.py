"""Modo demonstração (EGT_DEMO=1): respostas "oficiais" fictícias + um servidor local lento que serve arquivos pequenos.

Serve para mostrar a interface (progresso, offline, erros) sem internet e sem baixar nada de verdade.
Nunca é usado fora do modo demo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from ..languages import ALPHABETS
from . import defs
from .net import AllowList, Http, NetworkError

BLOCK = hashlib.sha256(b"egt-demo-blob").digest() * 2048          # 64 KiB


def blob_chunks(size: int, chunk: int = 65536):
    left = size
    while left > 0:
        n = min(chunk, left)
        yield BLOCK[:n] if n <= len(BLOCK) else (BLOCK * (n // len(BLOCK) + 1))[:n]
        left -= n


def blob_digests(size: int) -> tuple[str, str]:
    s2, s1 = hashlib.sha256(), hashlib.sha1(f"blob {size}\0".encode())
    for c in blob_chunks(size):
        s2.update(c)
        s1.update(c)
    return s2.hexdigest(), s1.hexdigest()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencioso
        pass

    def do_GET(self):
        m = re.match(r"^/blob/(\d+)", self.path)
        if not m:
            self.send_error(404)
            return
        size = int(m.group(1))
        rate = float(os.environ.get("EGT_DEMO_RATE", "1500000"))
        start = 0
        rng = self.headers.get("Range")
        if rng:
            mm = re.match(r"bytes=(\d+)-", rng)
            if mm:
                start = min(int(mm.group(1)), size)
        self.send_response(206 if start else 200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size - start))
        if start:
            self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
        self.end_headers()
        sent = 0
        try:
            for c in blob_chunks(size):
                lo, hi = sent, sent + len(c)
                sent = hi
                if hi <= start:
                    continue
                c = c[max(0, start - lo):]
                self.wfile.write(c)
                time.sleep(len(c) / rate)
        except (BrokenPipeError, ConnectionResetError):
            pass


class DemoHttp(Http):
    def __init__(self, demo: "DemoSource"):
        super().__init__(AllowList(allow_local=True), timeout=8.0)
        self.demo = demo

    # ---- tamanhos "oficiais" fictícios
    def size_for(self, url: str) -> int:
        u = url.lower()
        if "python-" in u:
            return 9_000_000
        if "tesseract-ocr-w64" in u:
            return 6_500_000
        if "ollamasetup" in u:
            return 12_000_000
        if u.endswith(".traineddata"):
            return {"jpn": 2_471_260, "por": 1_982_756}.get(u.rsplit("/", 1)[-1][:3], 1_700_000)
        if u.endswith(".argosmodel"):
            return 7_800_000
        return 1_200_000

    def _off(self):
        if self.demo.offline:
            raise NetworkError("sem internet ou servidor inacessível", offline=True)

    def get_json(self, url: str, limit: int = 8_000_000):
        self._off()
        self.allow.check(url)
        if "pypi.org/pypi/" in url:
            pkg = url.split("/pypi/")[1].split("/")[0]
            size = self.size_for("x.whl")
            sha2, _ = blob_digests(size)
            return {"info": {"version": "9.9.9"},
                    "urls": [{"packagetype": "bdist_wheel", "filename": f"{pkg}-9.9.9-py3-none-any.whl",
                              "url": f"https://files.pythonhosted.org/packages/demo/{pkg}-9.9.9-py3-none-any.whl",
                              "size": size, "digests": {"sha256": sha2}}]}
        if "tessdata_fast/contents" in url:
            files = []
            for code, _ in defs.lang_items():
                size = self.size_for(f"{code}.traineddata")
                files.append({"name": f"{code}.traineddata", "size": size, "sha": blob_digests(size)[1],
                              "download_url": f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{code}.traineddata"})
            return files
        if "releases/latest" in url:
            size = self.size_for("OllamaSetup.exe")
            return {"tag_name": "v0.40.6", "assets": [{"name": "OllamaSetup.exe", "size": size,
                    "digest": "sha256:" + blob_digests(size)[0],
                    "browser_download_url": "https://github.com/ollama/ollama/releases/download/v0.40.6/OllamaSetup.exe"}]}
        if "argospm-index" in url:
            return [{"from_code": a, "from_name": an, "to_code": b, "to_name": bn, "package_version": "1.9",
                     "links": [f"https://argos-net.com/v1/translate-{a}_{b}-1_9.argosmodel"]}
                    for a, an, b, bn in (("en", "English", "pt", "Portuguese"), ("pt", "Portuguese", "en", "English"),
                                         ("ja", "Japanese", "en", "English"), ("en", "English", "ja", "Japanese"),
                                         ("es", "Spanish", "en", "English"))]
        if "registry.ollama.ai" in url:
            return {"config": {"size": 1429}, "layers": [{"size": 770_000_000}, {"size": 7711}, {"size": 6016}]}
        raise NetworkError("HTTP 404", status=404)

    def get_text(self, url: str, limit: int = 4_000_000) -> str:
        self._off()
        self.allow.check(url)
        if "python.org/ftp/python" in url:
            return '<a href="3.12.14/">3.12.14/</a><a href="3.12.15/">3.12.15/</a>'
        if "uni-mannheim" in url:
            return '<a href="tesseract-ocr-w64-setup-5.5.0.20241111.exe">x</a>'
        raise NetworkError("HTTP 404", status=404)

    def head(self, url: str) -> dict:
        self._off()
        self.allow.check(url)
        return {"content-length": str(self.size_for(url)), "_status": 200, "_url": url}

    def content_length(self, url: str) -> Optional[int]:
        try:
            return int(self.head(url)["content-length"])
        except NetworkError:
            return None

    def open_stream(self, url: str, start: int = 0):
        self._off()
        self.allow.check(url)
        req = urllib.request.Request(f"{self.demo.base}/blob/{self.size_for(url)}",
                                     headers={"Range": f"bytes={start}-"} if start else {})
        return urllib.request.urlopen(req, timeout=10)


class DemoSource:
    active = True

    def __init__(self):
        self.offline = False
        self.python = False
        self.ollama_up = True
        self.models: list[dict] = [{"name": "llama3.2:1b", "size": 1_300_000_000}]
        self.installed_log: list[str] = []
        self.opened: list[str] = []
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._srv.daemon_threads = True
        self.base = f"http://127.0.0.1:{self._srv.server_address[1]}"
        threading.Thread(target=self._srv.serve_forever, name="egt-demo-files", daemon=True).start()
        self.http = DemoHttp(self)

    def close(self) -> None:
        self._srv.shutdown()

    def pythons(self) -> list:
        from .sysinfo import PyInfo
        import platform
        return [PyInfo("C:\\Python312\\python.exe", platform.python_version(), True)] if self.python else []

    def ollama_state(self) -> dict:
        return {"server": self.ollama_up, "version": "0.40.6" if self.ollama_up else "", "models": list(self.models),
                "base": "http://127.0.0.1:11434"}

    def pull(self, job, name: str) -> None:
        total = 120_000_000
        job.total, job.phase = total, "downloading"
        while job.done < total:
            if job.cancel.is_set():
                return
            job.done = min(total, job.done + 6_000_000)
            if job.publish:
                job.publish()
            time.sleep(0.25)
        self.models.append({"name": name if ":" in name else name + ":latest", "size": total})

    def delete(self, name: str) -> dict:
        self.models = [m for m in self.models if m["name"] not in (name, name + ":latest")]
        return {"removed": 1}

    def startfile(self, path: str) -> None:
        self.opened.append(path)

    def stream(self, cmd, on_line, cancel) -> int:
        """Finge o pip: mostra linhas por ~1,5 s e cria um pacote de mentira na pasta do usuário."""
        from pathlib import Path
        name = re.split(r"[=<>\[]", cmd[-1])[0]
        target = Path(cmd[cmd.index("--target") + 1])
        for i in range(6):
            if cancel.is_set():
                return -1
            on_line(f"Collecting {name}" if i == 0 else "Installing collected packages" if i > 3 else "Downloading ...")
            time.sleep(0.25)
        comp = next((c for c in defs.ALL if getattr(c, "pkg", "") == name), None)
        mod = getattr(comp, "module", name.replace("-", "_"))
        norm = re.sub(r"[-_.]+", "_", name)
        (target / mod).mkdir(parents=True, exist_ok=True)
        (target / mod / "__init__.py").write_text("# pacote de demonstração\n")
        di = target / f"{norm}-9.9.9.dist-info"
        di.mkdir(exist_ok=True)
        (di / "METADATA").write_text(f"Name: {name}\nVersion: 9.9.9\n")
        (di / "RECORD").write_text(f"{mod}/__init__.py,,\n{norm}-9.9.9.dist-info/METADATA,,\n{norm}-9.9.9.dist-info/RECORD,,\n")
        return 0
