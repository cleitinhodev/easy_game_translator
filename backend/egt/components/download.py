"""Motor de download: streaming com progresso (bytes/total, velocidade, ETA), cancelar, retomar, verificação de hash.

Só baixa de hosts oficiais (ver net.AllowList). Cada download é um Job em thread própria; o progresso sai por `emit`
(eventos do WebSocket). Nunca executa o arquivo baixado.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .net import Http, NetworkError

log = logging.getLogger(__name__)

SAFE_NAME = re.compile(r"[^A-Za-z0-9._+\-]")


def safe_filename(name: str) -> str:
    """Nome de arquivo sem diretórios/caracteres perigosos."""
    base = os.path.basename(name.replace("\\", "/")).strip(". ")
    base = SAFE_NAME.sub("_", base)
    return base[:120] or "download.bin"


@dataclass
class Expect:
    """Verificação de integridade vinda da fonte oficial (quando existir)."""
    sha256: str = ""
    git_blob_sha1: str = ""      # GitHub: sha1("blob <tamanho>\0"+dados)
    size: int = 0


@dataclass
class Job:
    id: str
    component: str
    item: str
    label: str
    url: str
    dest: Path
    expect: Expect = field(default_factory=Expect)
    state: str = "queued"        # queued | running | done | error | cancelled
    done: int = 0
    total: int = 0
    speed: float = 0.0
    eta: Optional[float] = None
    error: str = ""
    remedy: str = ""
    verified: str = ""           # 'sha256' | 'git-sha1' | ''
    phase: str = "downloading"   # downloading | installing | working | done
    installer: bool = False      # o arquivo baixado é um instalador (a UI oferece "Abrir instalador", com confirmação)
    started: float = 0.0
    post: Optional[Callable[["Job"], None]] = None      # roda depois do download verificado (ex.: pip, importar pacote)
    task: Optional[Callable[["Job"], None]] = None      # trabalho sem arquivo (ex.: ollama pull)
    publish: Optional[Callable[[], None]] = None        # publica o progresso atual (tarefas chamam de tempos em tempos)
    cancel: threading.Event = field(default_factory=threading.Event)

    def view(self) -> dict:
        return {"id": self.id, "component": self.component, "item": self.item, "label": self.label,
                "state": self.state, "done": self.done, "total": self.total, "speed": round(self.speed),
                "eta": None if self.eta is None else round(self.eta, 1), "error": self.error,
                "remedy": self.remedy, "verified": self.verified, "dest": str(self.dest), "phase": self.phase,
                "installer": self.installer,
                "host": re.sub(r"^https?://([^/:]+).*$", r"\1", self.url)}


class JobFailed(Exception):
    """Falha esperada de uma etapa pós-download/tarefa: mensagem + o que o usuário pode fazer."""

    def __init__(self, msg: str, remedy: str = ""):
        super().__init__(msg)
        self.remedy = remedy


class DownloadManager:
    def __init__(self, http: Http, downloads_dir: Callable[[], Path], emit: Callable[[dict], None] = lambda e: None,
                 on_done: Optional[Callable[[Job], None]] = None, chunk: int = 64 * 1024):
        self.http, self._dir, self.emit, self.on_done, self.chunk = http, downloads_dir, emit, on_done, chunk
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # -- API
    def start(self, component: str, item: str, label: str, url: str, filename: str,
              expect: Optional[Expect] = None, dest_dir: Optional[Path] = None,
              post: Optional[Callable[[Job], None]] = None) -> Job:
        self.http.allow.check(url)                       # rejeita host não oficial ANTES de criar o job
        d = Path(dest_dir) if dest_dir else self._dir()
        d.mkdir(parents=True, exist_ok=True)
        dest = d / safe_filename(filename)
        if d.resolve() not in dest.resolve().parents:
            raise ValueError("destino fora da pasta de downloads")
        with self._lock:
            for j in self.jobs.values():                 # um por vez por item
                if j.component == component and j.item == item and j.state in ("queued", "running"):
                    return j
            job = Job(uuid.uuid4().hex[:12], component, item, label, url, dest, expect or Expect(), post=post)
            self.jobs[job.id] = job
            job.publish = lambda j=job: self._publish(j)
            if len(self.jobs) > 60:                      # não cresce sem limite
                for k in [k for k, v in self.jobs.items() if v.state in ("done", "error", "cancelled")][:20]:
                    self.jobs.pop(k, None)
        threading.Thread(target=self._run, args=(job,), name=f"egt-dl-{job.id}", daemon=True).start()
        self._publish(job)
        return job

    def start_task(self, component: str, item: str, label: str, fn: Callable[[Job], None]) -> Job:
        """Tarefa sem download de arquivo (ex.: o Ollama baixa o modelo; progresso vem de `fn`)."""
        with self._lock:
            for j in self.jobs.values():
                if j.component == component and j.item == item and j.state in ("queued", "running"):
                    return j
            job = Job(uuid.uuid4().hex[:12], component, item, label, "", Path("."), task=fn, phase="working")
            self.jobs[job.id] = job
            job.publish = lambda j=job: self._publish(j)
        threading.Thread(target=self._run_task, args=(job,), name=f"egt-task-{job.id}", daemon=True).start()
        self._publish(job)
        return job

    def cancel(self, job_id: str) -> bool:
        j = self.jobs.get(job_id)
        if not j or j.state not in ("queued", "running"):
            return False
        j.cancel.set()
        return True

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def list(self) -> list[dict]:
        return [j.view() for j in self.jobs.values()]

    def wait(self, job_id: str, timeout: float = 30.0) -> Job:
        end = time.time() + timeout
        j = self.jobs[job_id]
        while j.state in ("queued", "running") and time.time() < end:
            time.sleep(0.02)
        return j

    # -- interno
    def _publish(self, j: Job) -> None:
        try:
            self.emit({"type": "component_job", "data": j.view()})
        except Exception:  # noqa: BLE001
            log.debug("emit falhou", exc_info=True)

    def _fail(self, j: Job, msg: str, remedy: str = "") -> None:
        j.state, j.error, j.remedy = "error", msg, remedy
        self._publish(j)

    def _run(self, j: Job) -> None:
        part = j.dest.with_name(j.dest.name + ".part")
        j.state, j.started = "running", time.time()
        self._publish(j)
        try:
            start = part.stat().st_size if part.exists() else 0
            resp = self.http.open_stream(j.url, start)
            try:
                code = getattr(resp, "status", 200)
                length = int(resp.headers.get("Content-Length") or 0)
                if start and code != 206:                # servidor ignorou o Range: recomeça do zero
                    start = 0
                j.total = (start + length) if length else (j.expect.size or 0)
                j.done = start
                mode = "ab" if start else "wb"
                last_pub, last_t, last_b = 0.0, time.time(), start
                with open(part, mode) as f:
                    while True:
                        if j.cancel.is_set():
                            j.state = "cancelled"
                            self._publish(j)
                            return                        # mantém o .part para retomar
                        buf = resp.read(self.chunk)
                        if not buf:
                            break
                        f.write(buf)
                        j.done += len(buf)
                        now = time.time()
                        if now - last_t >= 0.25:
                            j.speed = (j.done - last_b) / (now - last_t)
                            last_t, last_b = now, j.done
                            j.eta = ((j.total - j.done) / j.speed) if (j.speed > 0 and j.total) else None
                        if now - last_pub >= 0.2:
                            last_pub = now
                            self._publish(j)
            finally:
                resp.close()
            if j.total and j.done != j.total:
                raise NetworkError(f"download incompleto ({j.done}/{j.total} bytes)")
            ok, how, why = verify_file(part, j.expect)
            if not ok:
                part.unlink(missing_ok=True)
                self._fail(j, why, "O arquivo foi descartado. Tente baixar de novo; se repetir, use o link/comando manual.")
                return
            j.verified = how
            os.replace(part, j.dest)
            j.total, j.speed, j.eta = j.done, 0.0, 0.0
            if j.post:
                j.phase = "installing"
                self._publish(j)
                j.post(j)
                if j.cancel.is_set():
                    j.state = "cancelled"
                    self._publish(j)
                    return
            j.phase, j.state = "done", "done"
            self._publish(j)
            if self.on_done:
                try:
                    self.on_done(j)
                except Exception:  # noqa: BLE001
                    log.exception("pós-download falhou")
        except JobFailed as exc:
            self._fail(j, str(exc), exc.remedy)
        except NetworkError as exc:
            self._fail(j, "Sem internet ou servidor inacessível." if exc.offline else str(exc),
                       "Verifique a conexão e tente novamente (o download retoma de onde parou).")
        except OSError as exc:
            self._fail(j, f"Erro de disco: {exc}", "Confira o espaço livre e a permissão da pasta (botão Pasta).")
        except Exception as exc:  # noqa: BLE001
            log.exception("download falhou")
            self._fail(j, f"{type(exc).__name__}: {exc}")


def _run_task_impl(self: "DownloadManager", j: Job) -> None:
    j.state, j.started = "running", time.time()
    self._publish(j)
    try:
        j.task(j)  # type: ignore[misc]
        if j.cancel.is_set():
            j.state = "cancelled"
        else:
            j.phase, j.state = "done", "done"
            if j.total:
                j.done = j.total
        self._publish(j)
        if j.state == "done" and self.on_done:
            self.on_done(j)
    except JobFailed as exc:
        self._fail(j, str(exc), exc.remedy)
    except NetworkError as exc:
        self._fail(j, "Sem internet ou servidor inacessível." if exc.offline else str(exc),
                   "Verifique a conexão e tente novamente.")
    except Exception as exc:  # noqa: BLE001
        log.exception("tarefa falhou")
        self._fail(j, f"{type(exc).__name__}: {exc}")


DownloadManager._run_task = _run_task_impl  # type: ignore[attr-defined]


def verify_file(path: Path, exp: Expect) -> tuple[bool, str, str]:
    """(ok, método, motivo). Sem hash esperado => ok sem verificação ('')."""
    if exp.sha256:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        if h.hexdigest().lower() != exp.sha256.lower():
            return False, "", "SHA256 não confere com o publicado pela fonte oficial (arquivo corrompido ou adulterado)."
        return True, "sha256", ""
    if exp.git_blob_sha1:
        size = path.stat().st_size
        h = hashlib.sha1(f"blob {size}\0".encode())
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        if h.hexdigest().lower() != exp.git_blob_sha1.lower():
            return False, "", "Hash (git) não confere com o repositório oficial."
        return True, "git-sha1", ""
    return True, "", ""
