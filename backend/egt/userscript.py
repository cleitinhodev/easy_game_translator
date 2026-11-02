"""Modo Scripts: o usuário escolhe um arquivo (script/programa) que faz a tradução no lugar dos tradutores e da IA.

Contrato (versão 1) — o mesmo para canal único e duplo:

  ENTRADA  (stdin, UTF-8, um único JSON):
      {"version": 1, "mode": "single" | "dual",
       "inputs": ["texto 1"] ou ["texto do canal A", "texto do canal B"],
       "source_lang": "en" (ou "auto"), "target_lang": "pt",
       "channels": ["uni"] ou ["a", "b"]}

  SAÍDA    (stdout, UTF-8), uma das duas formas:
      1) JSON: {"outputs": ["tradução 1"]} ou {"outputs": ["tradução A", "tradução B"]}
               (opcional: {"error": "mensagem"} para avisar um erro ao usuário)
      2) Texto puro: canal único → todo o texto impresso;
                     canal duplo → as duas traduções separadas por uma linha contendo só  ---

  Código de saída diferente de 0 = erro (as últimas linhas do stderr aparecem para o usuário).

Camadas leves de segurança: sem shell; ambiente limpo (nenhuma chave, token ou variável do app vai para o script);
o usuário confirma o arquivo vendo o caminho e o SHA-256 — se o arquivo mudar, o EGT para e pede nova confirmação;
tempo limite (o processo é encerrado) e limite de tamanho da saída.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

CONTRACT_VERSION = 1
MAX_OUTPUT = 1_000_000          # bytes lidos do stdout (acima disso: erro)
MAX_STDERR = 64_000
MAX_INPUT_CHARS = 5000
MAX_FILE = 256 * 1024 * 1024    # só para calcular o hash (ninguém escolhe um script de 256 MB… mas um .exe pode ser grande)
SEPARATOR = "---"
DEFAULT_TIMEOUT = 15.0

# variáveis que o script recebe (o resto do ambiente do app NÃO passa: chaves, EGT_TOKEN, LD_LIBRARY_PATH do PyInstaller…)
_ENV_KEEP = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "HOME",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES", "PUBLIC", "USERNAME", "USER", "LOGNAME",
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
    "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "DISPLAY", "SHELL", "TERM",
}
_ENV_DENY_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH")


class ScriptError(Exception):
    """`code`: no_script | not_found | not_approved | hash_changed | no_runtime | unsupported | timeout | exit |
    bad_output | count | too_big | empty | script_error | start."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail

    def user_message(self) -> str:
        """Texto que vai para a interface (ela traduz pelo código entre colchetes)."""
        return f"Script [{self.code}]" + (f": {self.detail}" if self.detail else "")


@dataclass
class ScriptResult:
    outputs: list[str]
    ms: float = 0.0
    format: str = "json"          # json | text
    stderr: str = ""
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------ arquivo / hash
def sha256_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    p = Path(path)
    if p.stat().st_size > MAX_FILE:
        raise ScriptError("too_big", "arquivo grande demais")
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_hash_cache: dict[str, tuple[float, int, str]] = {}
_hash_lock = threading.Lock()


def current_hash(path: str) -> str:
    """SHA-256 com cache por (mtime, tamanho): não relê o arquivo inteiro a cada tradução."""
    st = os.stat(path)
    key = os.path.abspath(path)
    with _hash_lock:
        hit = _hash_cache.get(key)
        if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
            return hit[2]
    h = sha256_file(path)
    with _hash_lock:
        _hash_cache[key] = (st.st_mtime, st.st_size, h)
    return h


# ------------------------------------------------------------------ como executar
RUNTIMES = {   # extensão → (nome amigável, candidatos [(executável, args antes do arquivo)])
    ".py": ("Python", "python"),
    ".pyw": ("Python", "python"),
    ".js": ("Node.js", "node"), ".mjs": ("Node.js", "node"), ".cjs": ("Node.js", "node"),
    ".ps1": ("PowerShell", "powershell"),
    ".bat": ("cmd", "cmd"), ".cmd": ("cmd", "cmd"),
    ".sh": ("bash", "bash"),
    ".rb": ("Ruby", "ruby"), ".php": ("PHP", "php"), ".lua": ("Lua", "lua"), ".pl": ("Perl", "perl"),
    ".exe": ("", "direct"),
}


def _which(name: str) -> Optional[str]:
    p = shutil.which(name)
    if not p:
        return None
    if getattr(sys, "frozen", False):          # nunca usa o próprio executável do app como "python"
        try:
            if os.path.samefile(p, sys.executable):
                return None
        except OSError:
            pass
    return p


def _python_cmd() -> Optional[list[str]]:
    if os.name == "nt":
        py = _which("py")
        if py:
            return [py, "-3"]
        for n in ("python", "python3"):
            p = _which(n)
            if p and "WindowsApps" not in p:      # o "python.exe" falso da Microsoft Store só abre a loja
                return [p]
        p = _which("python")
        return [p] if p else None
    for n in ("python3", "python"):
        p = _which(n)
        if p:
            return [p]
    return None


def build_command(path: str) -> tuple[list[str], str]:
    """(argv, nome do interpretador). Levanta ScriptError(no_runtime/unsupported). Nunca usa shell."""
    ext = Path(path).suffix.lower()
    kind = RUNTIMES.get(ext, (None, None))[1]
    label = RUNTIMES.get(ext, ("", ""))[0]
    if kind == "python":
        cmd = _python_cmd()
        if not cmd:
            raise ScriptError("no_runtime", "Python")
        return cmd + ["-X", "utf8", path], "Python"
    if kind == "node":
        p = _which("node")
        if not p:
            raise ScriptError("no_runtime", "Node.js")
        return [p, path], label
    if kind == "powershell":
        p = _which("powershell") or _which("pwsh") if os.name == "nt" else _which("pwsh")
        if not p:
            raise ScriptError("no_runtime", "PowerShell")
        return [p, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", path], "PowerShell"
    if kind == "cmd":
        if os.name != "nt":
            raise ScriptError("unsupported", ext + " (Windows)")
        return [os.environ.get("COMSPEC") or "cmd.exe", "/d", "/c", path], "cmd"
    if kind == "bash":
        p = _which("bash") or _which("sh")
        if not p:
            raise ScriptError("no_runtime", "bash")
        return [p, path], "bash"
    if kind in ("ruby", "php", "lua", "perl"):
        p = _which(kind)
        if not p:
            raise ScriptError("no_runtime", label)
        return [p, path], label
    if kind == "direct":
        return [path], "exe"
    # sem extensão conhecida: executável direto (Linux: chmod +x com #!; Windows: só .exe/.com)
    if os.name == "nt":
        if ext == ".com":
            return [path], "exe"
        raise ScriptError("unsupported", ext or "?")
    if os.access(path, os.X_OK):
        return [path], "exe"
    try:
        with open(path, "rb") as fh:
            head = fh.read(2)
    except OSError:
        head = b""
    raise ScriptError("unsupported", (ext or "?") + (" (chmod +x)" if head == b"#!" else ""))


def runtime_info(path: str) -> dict:
    try:
        cmd, label = build_command(path)
        return {"runtime": label, "runtime_found": True, "runtime_path": cmd[0] if label != "exe" else ""}
    except ScriptError as exc:
        return {"runtime": exc.detail, "runtime_found": False, "runtime_error": exc.code}


def clean_env() -> dict[str, str]:
    env = {}
    for k, v in os.environ.items():
        ku = k.upper()
        if ku not in _ENV_KEEP or any(w in ku for w in _ENV_DENY_WORDS):
            continue
        env[k] = v
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["EGT_SCRIPT_CONTRACT"] = str(CONTRACT_VERSION)
    return env


# ------------------------------------------------------------------ execução
def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


def _reader(stream, cap: int, buf: list, flag: list) -> None:
    total = 0
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            if total < cap:
                buf.append(chunk[: cap - total])
            total += len(chunk)
            if total > cap:
                flag[0] = True
    except Exception:  # noqa: BLE001
        pass


def parse_output(raw: str, n: int) -> tuple[list[str], str]:
    """(saídas, formato). JSON {"outputs": [...]} ou texto puro (dual: separado por uma linha '---')."""
    text = raw.lstrip("\ufeff").strip()
    if not text:
        raise ScriptError("empty")
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            if data.get("error"):
                raise ScriptError("script_error", str(data["error"])[:300])
            outs = data.get("outputs")
            if isinstance(outs, str):
                outs = [outs]
            if not isinstance(outs, list) or not all(isinstance(o, str) for o in outs):
                raise ScriptError("bad_output", '"outputs" deve ser uma lista de textos')
            if len(outs) != n:
                raise ScriptError("count", f"{len(outs)}/{n}")
            return [o.strip() for o in outs], "json"
    if n == 1:
        return [text], "text"
    parts, cur = [], []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip() == SEPARATOR:
            parts.append("\n".join(cur).strip())
            cur = []
        else:
            cur.append(line)
    parts.append("\n".join(cur).strip())
    if len(parts) != n:
        raise ScriptError("count", f"{len(parts)}/{n}")
    return parts, "text"


def run_script(path: str, inputs: list[str], src: str = "", tgt: str = "pt", timeout: float = DEFAULT_TIMEOUT,
               channels: Optional[list[str]] = None) -> ScriptResult:
    """Executa o script uma vez com 1 ou 2 entradas. Não confere o hash (veja ScriptRunner)."""
    if not inputs or len(inputs) > 2:
        raise ScriptError("count", str(len(inputs)))
    if not path or not os.path.isfile(path):
        raise ScriptError("not_found", os.path.basename(path or ""))
    cmd, _label = build_command(path)
    payload = {"version": CONTRACT_VERSION, "mode": "dual" if len(inputs) == 2 else "single",
               "inputs": [str(x)[:MAX_INPUT_CHARS] for x in inputs], "source_lang": src or "auto",
               "target_lang": tgt, "channels": channels or (["a", "b"] if len(inputs) == 2 else ["uni"])}
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    kw: dict = {}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    t0 = time.perf_counter()
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=os.path.dirname(os.path.abspath(path)) or None, env=clean_env(), shell=False, **kw)
    except FileNotFoundError as exc:
        raise ScriptError("no_runtime", os.path.basename(cmd[0])) from exc
    except OSError as exc:
        raise ScriptError("start", f"{type(exc).__name__}: {exc}"[:200]) from exc
    out_buf: list = []
    err_buf: list = []
    out_big, err_big = [False], [False]
    th = [threading.Thread(target=_reader, args=(proc.stdout, MAX_OUTPUT, out_buf, out_big), daemon=True),
          threading.Thread(target=_reader, args=(proc.stderr, MAX_STDERR, err_buf, err_big), daemon=True)]
    for t in th:
        t.start()
    try:
        try:
            proc.stdin.write(data)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass                                     # o script não leu a entrada: tudo bem, vale o que ele imprimir
        try:
            proc.wait(timeout=max(0.5, float(timeout)))
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            raise ScriptError("timeout", f"{float(timeout):g} s")
        for t in th:
            t.join(2.0)
    finally:
        if proc.poll() is None:
            _kill_tree(proc)
    ms = (time.perf_counter() - t0) * 1000
    stderr = b"".join(err_buf).decode("utf-8", "replace")
    if out_big[0]:
        raise ScriptError("too_big", f"> {MAX_OUTPUT // 1000} KB")
    if proc.returncode != 0:
        tail = " ".join(stderr.strip().splitlines()[-3:])[:300]
        raise ScriptError("exit", f"{proc.returncode}" + (f" — {tail}" if tail else ""))
    raw = b"".join(out_buf).decode("utf-8", "replace")
    outs, fmt = parse_output(raw, len(inputs))
    return ScriptResult(outs, ms, fmt, stderr[-2000:])


class ScriptRunner:
    """Liga o script às configurações: caminho, hash aprovado e tempo limite (seção `script`)."""

    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self.last_error: Optional[ScriptError] = None
        self.last_ok = 0.0
        self.runs = 0

    def active(self) -> bool:
        return bool(self.settings.get("script.enabled", False))

    def path(self) -> str:
        return str(self.settings.get("script.path", "") or "")

    def check(self) -> str:
        """Confere arquivo + hash aprovado. Devolve o caminho. Levanta ScriptError."""
        path = self.path()
        if not path:
            raise ScriptError("no_script")
        if not os.path.isfile(path):
            raise ScriptError("not_found", os.path.basename(path))
        approved = str(self.settings.get("script.sha256", "") or "")
        if not approved:
            raise ScriptError("not_approved")
        try:
            h = current_hash(path)
        except OSError as exc:
            raise ScriptError("not_found", type(exc).__name__) from exc
        if h != approved:
            raise ScriptError("hash_changed", h[:12])
        return path

    def run(self, inputs: list[str], src: str, tgt: str, channels: Optional[list[str]] = None) -> ScriptResult:
        path = self.check()
        to = float(self.settings.get("script.timeout", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)
        with self._lock:                         # um de cada vez (canal A e B chegam juntos numa só chamada)
            try:
                res = run_script(path, inputs, src, tgt, to, channels)
            except ScriptError as exc:
                self.last_error = exc
                raise
            self.last_error = None
            self.last_ok = time.time()
            self.runs += 1
            return res

    def info(self) -> dict:
        path = self.path()
        d = {"enabled": self.active(), "path": path, "name": os.path.basename(path) if path else "",
             "sha256": str(self.settings.get("script.sha256", "") or ""), "exists": bool(path and os.path.isfile(path)),
             "timeout": float(self.settings.get("script.timeout", DEFAULT_TIMEOUT)), "runs": self.runs,
             "last_ok": self.last_ok, "error": self.last_error.code if self.last_error else "",
             "error_detail": self.last_error.detail if self.last_error else "", "current_sha256": "", "changed": False}
        if d["exists"]:
            try:
                d["current_sha256"] = current_hash(path)
                d["changed"] = bool(d["sha256"]) and d["current_sha256"] != d["sha256"]
                d["size"] = os.path.getsize(path)
            except (OSError, ScriptError):
                pass
            d.update(runtime_info(path))
        return d


def inspect(path: str) -> dict:
    """Dados para a confirmação (caminho, nome, tamanho, SHA-256, interpretador). Levanta ScriptError."""
    p = os.path.abspath(os.path.expanduser(path or ""))
    if not path or not os.path.isfile(p):
        raise ScriptError("not_found", os.path.basename(path or ""))
    d = {"path": p, "name": os.path.basename(p), "size": os.path.getsize(p), "sha256": sha256_file(p)}
    d.update(runtime_info(p))
    return d
