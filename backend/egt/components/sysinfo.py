"""Detecção do ambiente (Python do sistema, plataforma) e instalação de pacotes pip na pasta do usuário.

Tudo com listas de argumentos (sem shell). O pip só instala em `--target <pasta do usuário>`; nunca toca na
instalação do programa nem no Python do sistema.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

FROZEN = bool(getattr(sys, "frozen", False))
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def run_cmd(args: list[str], timeout: float = 15.0, env: Optional[dict] = None) -> tuple[int, str]:
    """Executa um programa (lista de argumentos, sem shell). Devolve (código, saída). Nunca levanta."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, shell=False,
                           creationflags=CREATE_NO_WINDOW, env=env, errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)


def runtime_tuple() -> tuple[int, int, int]:
    return sys.version_info[:3]


def platform_key() -> str:
    """Rótulo de plataforma de wheels do runtime do backend (ou '' se não soubermos)."""
    m = platform.machine().lower()
    if sys.platform == "win32":
        return "win_amd64" if m in ("amd64", "x86_64") else ("win_arm64" if "arm" in m else "")
    if sys.platform.startswith("linux"):
        return "manylinux2014_x86_64" if m in ("x86_64", "amd64") else ""
    if sys.platform == "darwin":
        return "macosx_11_0_arm64" if m == "arm64" else "macosx_10_9_x86_64"
    return ""


@dataclass
class PyInfo:
    exe: str
    version: str            # '3.12.7'
    has_pip: bool

    @property
    def major_minor(self) -> tuple[int, int]:
        a = self.version.split(".")
        return int(a[0]), int(a[1])


_PROBE = "import sys;print('%d.%d.%d' % sys.version_info[:3]);\ntry:\n import pip;print('pip')\nexcept Exception:\n print('nopip')"


def probe_python(exe: str) -> Optional[PyInfo]:
    rc, out = run_cmd([exe, "-c", _PROBE], timeout=12)
    if rc != 0:
        return None
    lines = out.strip().splitlines()
    if len(lines) < 2 or not re.match(r"^\d+\.\d+\.\d+$", lines[0].strip()):
        return None
    return PyInfo(exe, lines[0].strip(), lines[1].strip() == "pip")


def find_system_pythons(include_current: bool = True) -> list[PyInfo]:
    """Pythons instalados no computador (py launcher, PATH). Ignora o próprio executável congelado."""
    cands: list[str] = []
    if os.name == "nt":
        py = shutil.which("py")
        if py:
            rc, out = run_cmd([py, "-0p"], timeout=10)
            for line in out.splitlines():
                m = re.search(r"([A-Za-z]:\\[^\r\n]*python[^\r\n]*\.exe)\s*$", line.strip(), re.I)
                if m:
                    cands.append(m.group(1))
    for name in ("python3.12", "python3", "python"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    if include_current and not FROZEN and sys.executable:
        cands.insert(0, sys.executable)
    seen, out = set(), []
    for c in cands:
        key = os.path.normcase(os.path.abspath(c))
        if key in seen or "windowsapps" in key.lower():       # atalho da Microsoft Store não é um Python real
            continue
        seen.add(key)
        info = probe_python(c)
        if info:
            out.append(info)
    return out


def pick_pip_python(pythons: Optional[list[PyInfo]] = None) -> Optional[PyInfo]:
    """O melhor Python para rodar `pip --target`: o mesmo major.minor do runtime, com pip; senão qualquer um com pip >= 3.9."""
    pythons = find_system_pythons() if pythons is None else pythons
    mm = runtime_tuple()[:2]
    good = [p for p in pythons if p.has_pip and p.major_minor >= (3, 9)]
    same = [p for p in good if p.major_minor == mm]
    return (same or good or [None])[0]  # type: ignore[list-item]


def cross_flags(py: PyInfo) -> list[str]:
    """Se o Python do pip tem outra versão que o runtime do app, pede wheels do runtime (só binários)."""
    mm = runtime_tuple()[:2]
    if py.major_minor == mm:
        return []
    plat = platform_key()
    if not plat:
        return []
    return ["--python-version", f"{mm[0]}.{mm[1]}", "--implementation", "cp", "--abi", f"cp{mm[0]}{mm[1]}",
            "--platform", plat, "--only-binary=:all:"]


def pip_install_cmd(py: PyInfo, spec: str, target: Path, find_links: Optional[Path] = None) -> list[str]:
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._\-]*(\[[A-Za-z0-9,_\-]+\])?(==[A-Za-z0-9.!+_\-]+|<[0-9.]+|>=[0-9.]+)?$", spec):
        raise ValueError("especificação de pacote inválida")
    cmd = [py.exe, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade",
           "--progress-bar", "off", "--index-url", "https://pypi.org/simple", "--target", str(target)]
    if find_links:
        cmd += ["--find-links", str(find_links)]
    cmd += cross_flags(py)
    cmd.append(spec)
    return cmd


def run_streaming(cmd: list[str], on_line: Callable[[str], None], cancel: threading.Event, timeout: float = 1800.0) -> int:
    """Roda o comando lendo a saída linha a linha; encerra se `cancel`. Devolve o código de saída (-1 = cancelado)."""
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=False,
                             creationflags=CREATE_NO_WINDOW, errors="replace")
    except OSError as exc:
        on_line(f"erro ao iniciar: {exc}")
        return 127
    killer = threading.Timer(timeout, p.kill)
    killer.start()
    try:
        assert p.stdout is not None
        for line in p.stdout:
            on_line(line.rstrip())
            if cancel.is_set():
                p.terminate()
                return -1
        return p.wait()
    finally:
        killer.cancel()


# ---------------------------------------------------------------- wheels do PyPI
def _wheel_tags(fn: str) -> Optional[tuple[str, str, str]]:
    m = re.match(r"^.+?-.+?(?:-\d[^-]*)?-([^-]+)-([^-]+)-([^-]+)\.whl$", fn)
    return (m.group(1), m.group(2), m.group(3)) if m else None


def pick_wheel(urls: list[dict], pytag: Optional[str] = None, plat: Optional[str] = None) -> Optional[dict]:
    """Escolhe o arquivo do PyPI mais adequado ao runtime: py3-none-any > cpXY nativo > abi3. Sem wheel: None."""
    mm = runtime_tuple()
    pytag = pytag or f"cp{mm[0]}{mm[1]}"
    plat = plat if plat is not None else platform_key()
    best, best_score = None, -1
    for u in urls:
        fn = u.get("filename", "")
        if u.get("packagetype") != "bdist_wheel" or u.get("yanked"):
            continue
        t = _wheel_tags(fn)
        if not t:
            continue
        py, abi, pl = t
        pls = pl.split(".")
        score = -1
        if abi == "none" and pl == "any" and (py.startswith("py3") or py == "py2.py3"):
            score = 5
        else:
            plat_ok = any((p == plat) or (plat.startswith("manylinux") and p.startswith("manylinux") and "x86_64" in p)
                          or (plat.startswith("macosx") and p.startswith("macosx")) for p in pls) if plat else False
            if plat_ok and py == pytag:
                score = 10
            elif plat_ok and abi == "abi3" and py.startswith("cp3") and int(py[3:] or 0) <= mm[1]:
                score = 8
        if score > best_score:
            best, best_score = u, score
    return best


# ---------------------------------------------------------------- remover um pacote da pasta do usuário
def remove_pip_package(site_dir: Path, dist_name: str) -> int:
    """Apaga SOMENTE os arquivos listados no RECORD do pacote, desde que fiquem dentro de `site_dir`. Devolve a contagem."""
    site = site_dir.resolve()
    norm = re.sub(r"[-_.]+", "_", dist_name).lower()
    n = 0
    for di in list(site.glob("*.dist-info")):
        name = re.sub(r"[-_.]+", "_", di.name[: -len(".dist-info")].rpartition("-")[0]).lower()
        if name != norm:
            continue
        rec = di / "RECORD"
        files: list[Path] = []
        if rec.is_file():
            for line in rec.read_text(encoding="utf-8", errors="replace").splitlines():
                rel = line.split(",", 1)[0].strip()
                if not rel:
                    continue
                f = (site / rel).resolve()
                if site in f.parents:             # nunca sai da pasta do usuário (anti path-traversal)
                    files.append(f)
        for f in files:
            try:
                if f.is_file() or f.is_symlink():
                    f.unlink()
                    n += 1
            except OSError:
                pass
        shutil.rmtree(di, ignore_errors=True)
        # remove pastas vazias que sobraram
        dirs = sorted({f.parent for f in files}, key=lambda p: len(p.parts), reverse=True)
        for d in dirs:
            cur = d
            while cur != site and site in cur.parents:
                try:
                    cur.rmdir()
                except OSError:
                    break
                cur = cur.parent
    return n


def dist_in_dir(site_dir: Path, dist_name: str) -> Optional[str]:
    """Versão do pacote se estiver instalado em `site_dir` (lendo *.dist-info), senão None."""
    norm = re.sub(r"[-_.]+", "_", dist_name).lower()
    try:
        for di in site_dir.glob("*.dist-info"):
            base = di.name[: -len(".dist-info")]
            nm, _, ver = base.rpartition("-")
            if re.sub(r"[-_.]+", "_", nm).lower() == norm:
                return ver
    except OSError:
        pass
    return None
