"""Os componentes que o programa pode usar (e como detectar/baixar/remover cada um).

Regra de ouro: NADA aqui é necessário para o programa já instalado funcionar. São ajudas opcionais; tudo o que é
instalado vai para a pasta de componentes do usuário e pode ser removido sem afetar o resto.
"""
from __future__ import annotations

import importlib
import importlib.metadata as md
import importlib.util
import json
import logging
import os
import platform
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from ..languages import ALPHABETS, alphabet
from . import sysinfo
from .base import Avail, Component, ComponentError, Ctx, Detect, Plan, ver_tuple
from .download import Expect, Job, JobFailed
from .net import NetworkError

log = logging.getLogger(__name__)

PYPI_JSON = "https://pypi.org/pypi/{pkg}/json"
PYPI_VER_JSON = "https://pypi.org/pypi/{pkg}/{ver}/json"
PY_FTP = "https://www.python.org/ftp/python/"
GH_RELEASE = "https://api.github.com/repos/{repo}/releases/latest"
TESSDATA_API = "https://api.github.com/repos/tesseract-ocr/tessdata_fast/contents"
MANNHEIM = "https://digi.bib.uni-mannheim.de/tesseract/"
ARGOS_INDEX = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
OLLAMA_MANIFEST = "https://registry.ollama.ai/v2/library/{name}/manifests/{tag}"

MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._\-]*(/[a-z0-9._\-]+)?(:[A-Za-z0-9._\-]+)?$")


def _net_error(av: Avail, exc: NetworkError) -> Avail:
    av.ok = False
    av.offline = exc.offline
    av.error = "offline" if exc.offline else ("rate_limit" if exc.status in (403, 429) else "unavailable")
    return av


def _module_present(name: str) -> bool:
    try:
        importlib.invalidate_caches()
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


# ======================================================================= Python
class PythonComp(Component):
    id, category = "python", "runtime"

    def detect(self, ctx: Ctx) -> Detect:
        sys_py = ctx.pythons()
        runtime = platform.python_version()
        extra = {"system": [{"version": p.version, "path": p.exe, "pip": p.has_pip} for p in sys_py],
                 "runtime": runtime, "frozen": ctx.frozen}
        best = sysinfo.pick_pip_python(sys_py)
        if ctx.frozen:
            return Detect(True, runtime, str(best.exe) if best else "", builtin=True, extra=extra)
        return Detect(True, runtime, sys.executable, extra=extra)

    def offer(self, ctx: Ctx, det: Detect) -> bool:
        return bool(det.builtin) and not any(p["pip"] for p in det.extra.get("system", []))

    def blocker(self, ctx: Ctx, item: str = "") -> str:
        return "" if ctx.plat == "win32" else "package_manager"

    def check(self, ctx: Ctx) -> Avail:
        av = Avail()
        if ctx.plat != "win32":
            av.error, av.note = "", "no_installer"
            return av
        try:
            html = ctx.http.get_text(PY_FTP)
            vers = sorted({m for m in re.findall(r'href="(3\.12\.\d+)/"', html)}, key=ver_tuple, reverse=True)
            for v in vers[:8]:                       # versões antigas só têm código-fonte: procura a mais nova com instalador
                url = f"{PY_FTP}{v}/python-{v}-amd64.exe"
                size = ctx.http.content_length(url)
                if size:
                    av.ok, av.latest, av.size, av.url = True, v, size, url
                    av.filename = f"python-{v}-amd64.exe"
                    return av
            av.error = "unavailable"
        except NetworkError as exc:
            _net_error(av, exc)
        return av

    def plan(self, ctx: Ctx, item: str, av: Avail) -> Plan:
        if not av.ok:
            raise ComponentError("not_checked")
        return Plan(f"Python {av.latest}", av.url, av.filename, av.expect, ctx.store.downloads(), is_installer=True)

    def removable(self, ctx, det, item=""):
        return bool(list(ctx.store.downloads().glob("python-*.exe")))

    def remove(self, ctx, item=""):
        n = 0
        for f in ctx.store.downloads().glob("python-*.exe*"):
            f.unlink(missing_ok=True)
            n += 1
        return {"removed": n}

    def manual(self, ctx):
        return {"links": [("python.org/downloads", "https://www.python.org/downloads/windows/")],
                "commands": [("winget", "winget install -e --id Python.Python.3.12"), ("py", "py -0p")],
                "notes": ["py_note"]}


# ======================================================================= pacotes pip
class PipComponent(Component):
    pkg: str = ""
    module: str = ""
    pin: str = ""                    # versão fixa (compatível com o que vem no programa)
    extra_pkgs: tuple = ()
    windows_only: bool = False
    voice: bool = False

    def _version(self, ctx: Ctx) -> tuple[str, bool, str]:
        """(versão, na pasta do usuário?, local)"""
        sp = ctx.store.site_packages()
        user_ver = sysinfo.dist_in_dir(sp, self.pkg)
        loc = ""
        try:
            spec = importlib.util.find_spec(self.module)
            loc = (spec.origin or "") if spec else ""
        except (ImportError, ValueError, AttributeError):
            spec = None
        in_user = False
        if loc:
            try:
                in_user = sp.resolve() in Path(loc).resolve().parents
            except OSError:
                pass
        ver = ""
        try:
            ver = md.version(self.pkg)
        except Exception:  # noqa: BLE001
            ver = user_ver or ""
        return ver, in_user, loc

    def detect(self, ctx: Ctx) -> Detect:
        if self.windows_only and ctx.plat != "win32":
            return Detect(False, detail="not_windows")
        if not _module_present(self.module):
            return Detect(False)
        ver, in_user, loc = self._version(ctx)
        return Detect(True, ver, loc, builtin=(ctx.frozen and not in_user), in_user_dir=in_user)

    def blocker(self, ctx: Ctx, item: str = "") -> str:
        if self.windows_only and ctx.plat != "win32":
            return "not_windows"
        if ctx.frozen and not self.frozen_ok:
            return "frozen_unsupported"
        if sysinfo.pick_pip_python(ctx.pythons()) is None and not (ctx.demo and getattr(ctx.demo, "active", False)):
            return "needs_python"
        return ""

    def check(self, ctx: Ctx) -> Avail:
        av = Avail()
        if self.windows_only and ctx.plat != "win32":
            av.error = "not_windows"
            return av
        try:
            data = ctx.http.get_json(PYPI_VER_JSON.format(pkg=self.pkg, ver=self.pin) if self.pin
                                     else PYPI_JSON.format(pkg=self.pkg))
        except NetworkError as exc:
            return _net_error(av, exc)
        av.latest = (data.get("info") or {}).get("version", "") or self.pin
        w = sysinfo.pick_wheel(data.get("urls") or [])
        if w:
            av.ok, av.size, av.url, av.filename = True, int(w.get("size") or 0), w["url"], w["filename"]
            av.expect = Expect(sha256=(w.get("digests") or {}).get("sha256", ""), size=int(w.get("size") or 0))
        else:
            av.error, av.note = "no_binary", ""
        if self.heavy:
            av.note = "heavy"
        return av

    def spec(self) -> str:
        return f"{self.pkg}=={self.pin}" if self.pin else self.pkg

    def plan(self, ctx: Ctx, item: str, av: Avail) -> Plan:
        if not av.ok:
            raise ComponentError("not_checked")
        return Plan(self.pkg, av.url, av.filename, av.expect, ctx.store.downloads(), post=self._post(ctx))

    def _post(self, ctx: Ctx) -> Callable[[Job], None]:
        def run(job: Job) -> None:
            py = sysinfo.pick_pip_python(ctx.pythons(refresh=True))
            if py is None:
                raise JobFailed("needs_python", "Instale o Python do computador (linha 'Python') e tente de novo.")
            sp = ctx.store.site_packages()
            sp.mkdir(parents=True, exist_ok=True)
            specs = [self.spec(), *[p for p in self.extra_pkgs]]
            tail: list[str] = []

            def on_line(ln: str) -> None:
                if ln:
                    tail.append(ln)
                    del tail[:-40]
                    job.phase = "installing"

            for spec in specs:
                cmd = sysinfo.pip_install_cmd(py, spec, sp, find_links=ctx.store.downloads())
                rc = ctx.stream(cmd, on_line, job.cancel)
                if rc == -1:
                    return
                if rc != 0:
                    raise JobFailed(*_pip_message("\n".join(tail)))
            importlib.invalidate_caches()
        return run

    def removable(self, ctx, det, item=""):
        return bool(det.in_user_dir or sysinfo.dist_in_dir(ctx.store.site_packages(), self.pkg))

    def remove(self, ctx, item=""):
        n = sysinfo.remove_pip_package(ctx.store.site_packages(), self.pkg)
        for p in self.extra_pkgs:
            n += sysinfo.remove_pip_package(ctx.store.site_packages(), re.split(r"[=<>\[]", p)[0])
        importlib.invalidate_caches()
        return {"removed": n}

    def manual(self, ctx):
        pk = " ".join([self.spec(), *self.extra_pkgs])
        target = str(ctx.store.site_packages())
        cmds = [("pip", f"py -m pip install {pk}")]
        if self.frozen_ok or not ctx.frozen:          # no programa instalado, a pasta do app não carrega este pacote
            cmds.insert(0, ("pip (pasta do app)", f'py -m pip install --target "{target}" {pk}'))
        return {"links": [(f"pypi.org/project/{self.pkg}", f"https://pypi.org/project/{self.pkg}/")],
                "commands": cmds,
                "notes": (["frozen_note"] if not self.frozen_ok else [])}


def _pip_message(text: str) -> tuple[str, str]:
    low = text.lower()
    if "no matching distribution" in low or "could not find a version" in low:
        return ("Não há uma versão pronta deste item para o seu computador.",
                "Veja 'Como instalar manualmente' para as opções.")
    if any(k in low for k in ("failed to establish", "connection", "temporary failure", "timed out", "max retries")):
        return ("Sem internet ou o servidor oficial não respondeu.", "Verifique a conexão e tente de novo.")
    if "permission" in low or "access is denied" in low:
        return ("Sem permissão para gravar na pasta de componentes.", "Troque o local em 'Mudar pasta…'.")
    last = [ln for ln in text.splitlines() if ln.strip()][-3:]
    return ("Não consegui instalar. " + " ".join(last)[:300], "Nada foi alterado no programa. Veja 'Como instalar manualmente'.")


class RapidOcrComp(PipComponent):
    id, category = "rapidocr", "ocr"
    # rapidocr-onnxruntime só existe até o Python 3.12; no 3.13+ (ex.: Linux a partir do código) usa o "rapidocr" v3 + onnxruntime
    if sys.version_info < (3, 13):
        pkg, module = "rapidocr-onnxruntime", "rapidocr_onnxruntime"
    else:
        pkg, module, extra_pkgs = "rapidocr", "rapidocr", ("onnxruntime",)

    def detect(self, ctx):
        # aceita qualquer um dos dois pacotes já instalados (o código de OCR usa o que encontrar)
        for pkg, module in (("rapidocr-onnxruntime", "rapidocr_onnxruntime"), ("rapidocr", "rapidocr")):
            if _module_present(module):
                self.pkg, self.module = pkg, module
                break
        return super().detect(ctx)
    frozen_ok = False                          # no Windows ele já vem dentro do programa

    def needed(self, ctx, det):
        return ctx.usage().get("ocr_engine") == "rapidocr" and not det.installed

    def blocker(self, ctx, item=""):
        if ctx.frozen:
            return "builtin"
        return super().blocker(ctx, item)

    def add_files(self, ctx):
        return {"key": "files_rapid", "exts": [".onnx"]}


class EasyOcrComp(PipComponent):
    id, category, pkg, module = "easyocr", "ocr", "easyocr", "easyocr"
    frozen_ok, heavy = False, True

    def needed(self, ctx, det):
        return ctx.usage().get("ocr_engine") == "easyocr" and not det.installed

    def items(self, ctx, det, av):
        if not det.installed:
            return []
        return [{"id": "models", "installed": None, "size": None, "needed": False}]

    def plan(self, ctx, item, av):
        if item != "models":
            return super().plan(ctx, item, av)
        if not _module_present("easyocr"):
            raise ComponentError("needs_module")
        codes = list(alphabet(ctx.usage().get("alphabet") or "abc(EN)").easy)
        mdir = ctx.store.ensure("easyocr")

        def task(job: Job) -> None:
            try:
                import easyocr  # type: ignore
                job.phase = "working"
                easyocr.Reader(codes, gpu=False, model_storage_directory=str(mdir), download_enabled=True, verbose=False)
            except Exception as exc:  # noqa: BLE001
                raise JobFailed(f"Não consegui baixar os modelos: {exc}", "Veja 'Como instalar manualmente'.") from exc
        return Plan("EasyOCR (" + ", ".join(codes) + ")", task=task)

    def add_files(self, ctx):
        return {"key": "files_easy", "exts": [".pth"]}

    def blocker(self, ctx, item=""):
        if item == "models":
            return "" if _module_present("easyocr") else "needs_module"
        return super().blocker(ctx, item)


class PaddleComp(PipComponent):
    id, category, pkg, module = "paddleocr", "ocr", "paddleocr", "paddleocr"
    extra_pkgs = ("paddlepaddle",)
    frozen_ok, heavy = False, True

    def needed(self, ctx, det):
        return ctx.usage().get("ocr_engine") == "paddleocr" and not det.installed


class WinOcrComp(PipComponent):
    id, category, pkg, module = "winocr", "ocr", "winocr", "winocr"
    frozen_ok, windows_only = False, True

    def needed(self, ctx, det):
        return ctx.usage().get("ocr_engine") == "winocr" and not det.installed

    def manual(self, ctx):
        m = super().manual(ctx)
        m["links"] += [("Microsoft Learn", "https://learn.microsoft.com/windows/powertoys/text-extractor#supported-languages")]
        m["commands"] = [("PowerShell (administrador) — listar", 'Get-WindowsCapability -Online -Name "Language.OCR*"'),
                         ("PowerShell (administrador) — instalar pt-BR", 'Add-WindowsCapability -Online -Name "Language.OCR~~~pt-BR~~~0.0.1.0"'),
                         *m["commands"]]
        return m


class OpenCvComp(PipComponent):
    id, category, pkg, module = "opencv", "ocr", "opencv-python-headless", "cv2"
    pin = "4.10.0.84"                          # mesma versão testada junto com o resto do programa


class GttsComp(PipComponent):
    id, category, pkg, module = "gtts", "voice", "gTTS", "gtts"


class SpeechComp(PipComponent):
    id, category, pkg, module = "speechrecognition", "voice", "SpeechRecognition", "speech_recognition"


# ======================================================================= Tesseract (programa)
def tesseract_exe(ctx: Ctx) -> Optional[str]:
    from ..ocr.tesseract import find_tesseract
    return find_tesseract(ctx.get_setting("ocr.tesseract_path", "") or "")


class TesseractComp(Component):
    id, category = "tesseract", "ocr"

    def detect(self, ctx: Ctx) -> Detect:
        exe = tesseract_exe(ctx)
        if not exe:
            return Detect(False)
        rc, out = ctx.run([exe, "--version"], timeout=8)
        m = re.search(r"tesseract\s+v?([0-9][^\s]*)", out)
        in_user = False
        try:
            in_user = ctx.store.dir_for("tesseract").resolve() in Path(exe).resolve().parents
        except OSError:
            pass
        return Detect(True, m.group(1) if m else "", exe, in_user_dir=in_user)

    def needed(self, ctx, det):
        return ctx.usage().get("ocr_engine") == "tesseract" and not det.installed

    def blocker(self, ctx, item=""):
        return "" if ctx.plat == "win32" else "package_manager"

    def check(self, ctx):
        av = Avail()
        if ctx.plat != "win32":
            av.note = "no_installer"
            return av
        try:
            html = ctx.http.get_text(MANNHEIM)
            vers = sorted(set(re.findall(r"tesseract-ocr-w64-setup-([0-9][0-9.]*[0-9])\.exe", html)), key=ver_tuple, reverse=True)
            if not vers:
                av.error = "unavailable"
                return av
            v = vers[0]
            fn = f"tesseract-ocr-w64-setup-{v}.exe"
            url = MANNHEIM + fn
            av.ok, av.latest, av.url, av.filename = True, v, url, fn
            av.size = ctx.http.content_length(url)
            av.note = "no_hash"          # o site do mantenedor não publica hash: a UI orienta checar a assinatura
        except NetworkError as exc:
            _net_error(av, exc)
        return av

    def plan(self, ctx, item, av):
        if not av.ok:
            raise ComponentError("not_checked")
        return Plan("Tesseract OCR " + av.latest, av.url, av.filename, av.expect, ctx.store.downloads(), is_installer=True)

    def removable(self, ctx, det, item=""):
        return bool(det.in_user_dir)

    def remove(self, ctx, item=""):
        d = ctx.store.dir_for("tesseract")
        n = 0
        if d.is_dir():
            for f in d.iterdir():
                if f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)
                else:
                    f.unlink(missing_ok=True)
                n += 1
        return {"removed": n}

    def manual(self, ctx):
        return {"links": [("UB Mannheim (Windows)", "https://github.com/UB-Mannheim/tesseract/wiki"),
                          ("Documentação oficial", "https://tesseract-ocr.github.io/tessdoc/Installation.html")],
                "commands": [("winget", "winget install -e --id UB-Mannheim.TesseractOCR"),
                             ("Linux (Debian/Ubuntu)", "sudo apt install tesseract-ocr"),
                             ("macOS (Homebrew)", "brew install tesseract")],
                "notes": ["tess_exe_note"]}

    def add_files(self, ctx):
        return {"key": "files_tess_exe", "exts": [".exe", ".dll"]}


# ======================================================================= Tesseract (idiomas)
def lang_items() -> list[tuple[str, str]]:
    """[(código tesseract, nome)] para os alfabetos que o programa conhece."""
    seen: dict[str, str] = {}
    for a in ALPHABETS.values():
        for code in a.tesseract.split("+"):
            seen.setdefault(code, a.title or a.key)
    return list(seen.items())


def system_tess_langs(ctx: Ctx) -> set[str]:
    exe = tesseract_exe(ctx)
    if not exe:
        return set()
    rc, out = ctx.run([exe, "--list-langs"], timeout=10)
    if rc != 0:
        return set()
    return {ln.strip() for ln in out.splitlines()[1:] if ln.strip() and " " not in ln.strip()}


class TessdataComp(Component):
    id, category = "tessdata", "ocr"

    def _user(self, ctx: Ctx) -> set[str]:
        d = ctx.store.tessdata_dir()
        try:
            return {f.stem for f in d.glob("*.traineddata")} if d.is_dir() else set()
        except OSError:
            return set()

    def detect(self, ctx):
        user = self._user(ctx)
        sysl = system_tess_langs(ctx)
        langs = sorted(user | sysl)
        return Detect(bool(langs), f"{len(langs)}", str(ctx.store.tessdata_dir()), in_user_dir=bool(user),
                      extra={"user": sorted(user), "system": sorted(sysl)})

    def needed(self, ctx, det):
        u = ctx.usage()
        if u.get("ocr_engine") != "tesseract":
            return False
        want = alphabet(u.get("alphabet") or "abc(EN)").tesseract
        have = set(det.extra.get("user", [])) | set(det.extra.get("system", []))
        return not all(c in have for c in want.split("+"))

    def items(self, ctx, det, av):
        have = set(det.extra.get("user", [])) | set(det.extra.get("system", []))
        want = set(alphabet(ctx.usage().get("alphabet") or "abc(EN)").tesseract.split("+")) \
            if ctx.usage().get("ocr_engine") == "tesseract" else set()
        out = []
        for code, name in lang_items():
            info = (av.items.get(code) if av else None) or {}
            out.append({"id": code, "name": name, "installed": code in have,
                        "user": code in set(det.extra.get("user", [])),
                        "size": info.get("size"), "needed": code in want and code not in have})
        return out

    def check(self, ctx):
        av = Avail()
        try:
            data = ctx.http.get_json(TESSDATA_API, limit=2_000_000)
        except NetworkError as exc:
            return _net_error(av, exc)
        files = {f["name"][:-len(".traineddata")]: f for f in data if isinstance(f, dict) and str(f.get("name", "")).endswith(".traineddata")}
        for code, _ in lang_items():
            f = files.get(code)
            if f:
                av.items[code] = {"size": int(f.get("size") or 0), "url": f.get("download_url") or "",
                                  "filename": f"{code}.traineddata",
                                  "expect": Expect(git_blob_sha1=f.get("sha", ""), size=int(f.get("size") or 0))}
        av.ok = bool(av.items)
        av.latest = "tessdata_fast"
        return av

    def plan(self, ctx, item, av):
        info = av.items.get(item)
        if not info or not re.match(r"^[A-Za-z0-9_]+$", item):
            raise ComponentError("unknown_item")
        return Plan(f"{item}.traineddata", info["url"], info["filename"], info["expect"], ctx.store.ensure("tessdata"))

    def removable(self, ctx, det, item=""):
        return (item in self._user(ctx)) if item else bool(self._user(ctx))

    def remove(self, ctx, item=""):
        if not item or not re.match(r"^[A-Za-z0-9_]+$", item):
            raise ComponentError("unknown_item")
        f = ctx.store.tessdata_dir() / f"{item}.traineddata"
        ok = f.is_file()
        f.unlink(missing_ok=True)
        return {"removed": int(ok)}

    def manual(self, ctx):
        return {"links": [("tessdata_fast (GitHub oficial)", "https://github.com/tesseract-ocr/tessdata_fast"),
                          ("Lista de idiomas", "https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html")],
                "commands": [("Linux", "sudo apt install tesseract-ocr-jpn   # troque jpn pelo idioma"),
                             ("winget (instalador inclui idiomas)", "winget install -e --id UB-Mannheim.TesseractOCR")],
                "notes": ["tessdata_note"]}

    def add_files(self, ctx):
        return {"key": "files_tessdata", "exts": [".traineddata"]}


# ======================================================================= Argos
class ArgosComp(PipComponent):
    id, category, pkg, module = "argos", "translation", "argostranslate", "argostranslate"
    frozen_ok, heavy = False, True

    def needed(self, ctx, det):
        u = ctx.usage()
        if "argos" not in (u.get("translation_enabled") or []):
            return False
        if not det.installed:
            return True
        return not det.extra.get("pairs")

    def detect(self, ctx):
        det = super().detect(ctx)
        if det.installed:
            try:
                from ..translate import argos
                det.extra["pairs"] = [list(p) for p in argos.installed_pairs()]
            except Exception:  # noqa: BLE001
                det.extra["pairs"] = []
        return det

    def items(self, ctx, det, av):
        inst = {tuple(p) for p in det.extra.get("pairs", [])}
        out = []
        for key, info in ((av.items if av else {}) or {}).items():
            a, b = key.split(">")
            out.append({"id": key, "name": f"{info.get('from_name', a)} → {info.get('to_name', b)}",
                        "installed": (a, b) in inst, "size": info.get("size"), "needed": False})
        return out

    def check(self, ctx):
        av = super().check(ctx)
        try:
            idx = ctx.http.get_json(ARGOS_INDEX, limit=4_000_000)
        except NetworkError as exc:
            if not av.ok and av.error in ("", "no_binary"):
                _net_error(av, exc)
            return av
        for e in idx if isinstance(idx, list) else []:
            try:
                key = f"{e['from_code']}>{e['to_code']}"
                link = (e.get("links") or [""])[0]
                av.items[key] = {"from_name": e.get("from_name"), "to_name": e.get("to_name"), "url": link,
                                 "filename": os.path.basename(urllib.parse.urlsplit(link).path) or f"{key}.argosmodel",
                                 "size": None, "version": e.get("package_version", "")}
            except (KeyError, TypeError):
                continue
        # tamanho só dos pares que o usuário usa (um HEAD cada)
        for key in self._wanted(ctx):
            self._size(ctx, av.items, key)
        av.ok = av.ok or bool(av.items)
        return av

    def _wanted(self, ctx: Ctx) -> list[str]:
        u = ctx.usage()
        s, t = u.get("src_lang") or "en", u.get("tgt") or "pt"
        return [f"{s}>{t}", f"{t}>{s}"] if s != t else []

    def _size(self, ctx: Ctx, items: dict, key: str) -> Optional[int]:
        info = items.get(key)
        if info and info.get("size") is None and info.get("url"):
            info["size"] = ctx.http.content_length(info["url"])
        return (info or {}).get("size")

    def check_item(self, ctx, item):
        try:
            idx = ctx.http.get_json(ARGOS_INDEX, limit=4_000_000)
        except NetworkError as exc:
            return {"error": "offline" if exc.offline else "unavailable"}
        for e in idx:
            if f"{e.get('from_code')}>{e.get('to_code')}" == item:
                link = (e.get("links") or [""])[0]
                return {"size": ctx.http.content_length(link) if link else None}
        return {}

    def blocker(self, ctx, item=""):
        if item and item != "pkg":
            return "" if _module_present("argostranslate") else "needs_module"
        return super().blocker(ctx, item)

    def plan(self, ctx, item, av):
        if not item or item == "pkg":
            return super().plan(ctx, item, av)
        info = av.items.get(item)
        if not info or not info.get("url"):
            raise ComponentError("unknown_item")
        if not _module_present("argostranslate"):
            raise ComponentError("needs_module")

        def post(job: Job) -> None:
            try:
                import argostranslate.package as ap  # type: ignore
                ap.install_from_path(str(job.dest))
                job.dest.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                raise JobFailed(f"Não consegui instalar o pacote de idioma: {exc}", "Veja 'Como instalar manualmente'.") from exc
        return Plan(f"Argos {item.replace('>', ' → ')}", info["url"], info["filename"], Expect(), ctx.store.downloads(), post=post)

    def removable(self, ctx, det, item=""):
        if item and item != "pkg":
            return any(f"{a}>{b}" == item for a, b in det.extra.get("pairs", []))
        return super().removable(ctx, det, item)

    def remove(self, ctx, item=""):
        if not item or item == "pkg":
            return super().remove(ctx, item)
        try:
            import argostranslate.package as ap  # type: ignore
            a, b = item.split(">")
            for pkg in ap.get_installed_packages():
                if pkg.from_code == a and pkg.to_code == b:
                    ap.uninstall(pkg)
                    return {"removed": 1}
        except Exception as exc:  # noqa: BLE001
            raise ComponentError("remove_failed", str(exc)) from exc
        return {"removed": 0}

    def rescan(self, ctx):
        """Importa arquivos .argosmodel colocados à mão na pasta do componente."""
        d = ctx.store.dir_for("argos")
        n = 0
        if _module_present("argostranslate") and d.is_dir():
            import argostranslate.package as ap  # type: ignore
            for f in sorted(d.glob("*.argosmodel")):
                try:
                    ap.install_from_path(str(f))
                    f.rename(f.with_suffix(".argosmodel.imported"))
                    n += 1
                except Exception:  # noqa: BLE001
                    log.warning("não importei %s", f.name)
        return {"imported": n}

    def add_files(self, ctx):
        return {"key": "files_argos", "exts": [".argosmodel"]}

    def manual(self, ctx):
        m = super().manual(ctx)
        m["links"].append(("Pacotes de idioma (Argos)", "https://www.argosopentech.com/argospm/index/"))
        return m


# ======================================================================= Ollama / Gemini
def _local_base(url: str) -> Optional[str]:
    p = urllib.parse.urlsplit(url or "http://localhost:11434")
    if p.scheme not in ("http", "https") or (p.hostname or "").lower() not in ("localhost", "127.0.0.1", "::1"):
        return None
    return f"{p.scheme}://{p.hostname if ':' not in (p.hostname or '') else '[' + p.hostname + ']'}:{p.port or 11434}"


def ollama_call(base: str, path: str, method: str = "GET", body: Optional[dict] = None, timeout: float = 2.5):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


SUGGESTED_MODELS = [("llama3.2:3b", "Llama 3.2 (3B)"), ("qwen2.5:3b", "Qwen 2.5 (3B)"),
                    ("gemma2:2b", "Gemma 2 (2B)"), ("llama3.2:1b", "Llama 3.2 (1B, leve)")]


def ollama_exe() -> Optional[str]:
    w = shutil.which("ollama")
    if w:
        return w
    la = os.environ.get("LOCALAPPDATA")
    if la:
        p = Path(la) / "Programs" / "Ollama" / "ollama.exe"
        if p.is_file():
            return str(p)
    return None


def models_dir() -> Path:
    env = os.environ.get("OLLAMA_MODELS")
    return Path(env) if env else Path.home() / ".ollama" / "models"


class OllamaComp(Component):
    id, category = "ollama", "ai"

    def _state(self, ctx: Ctx) -> dict:
        if ctx.demo and getattr(ctx.demo, "active", False):
            return ctx.demo.ollama_state()
        base = _local_base(ctx.get_setting("ai.ollama_url", "http://localhost:11434"))
        st = {"server": False, "version": "", "models": [], "base": base or ""}
        if not base:
            return st
        try:
            with ollama_call(base, "/api/version") as r:
                st["version"] = json.loads(r.read().decode()).get("version", "")
            st["server"] = True
            with ollama_call(base, "/api/tags") as r:
                st["models"] = [{"name": m.get("name", ""), "size": m.get("size")} for m in json.loads(r.read().decode()).get("models", [])]
        except Exception:  # noqa: BLE001
            pass
        return st

    def detect(self, ctx):
        st = self._state(ctx)
        exe = ollama_exe()
        return Detect(bool(st["server"] or exe), st["version"], exe or st["base"],
                      extra={"server": st["server"], "models": st["models"], "exe": bool(exe)})

    def _wanted(self, ctx):
        u = ctx.usage()
        return u.get("ollama_model") if (u.get("ai_enabled") and u.get("ai_provider") == "ollama") else ""

    def needed(self, ctx, det):
        u = ctx.usage()
        if not (u.get("ai_enabled") and u.get("ai_provider") == "ollama"):
            return False
        return not det.extra.get("server") or not self._has(det, u.get("ollama_model"))

    @staticmethod
    def _has(det, name) -> bool:
        names = {m["name"] for m in det.extra.get("models", [])}
        return bool(name) and (name in names or f"{name}:latest" in names)

    def items(self, ctx, det, av):
        out, seen = [], set()
        want = self._wanted(ctx)
        inst = {m["name"]: m.get("size") for m in det.extra.get("models", [])}
        for name, label in SUGGESTED_MODELS:
            info = (av.items.get(name) if av else None) or {}
            out.append({"id": name, "name": label, "installed": name in inst or f"{name}:latest" in inst,
                        "size": info.get("size"), "needed": bool(want) and name == want and name not in inst})
            seen.add(name)
        for name, size in inst.items():
            if name not in seen and name.replace(":latest", "") not in seen:
                out.append({"id": name, "name": name, "installed": True, "size": size, "needed": False})
        if want and want not in seen and want not in inst and f"{want}:latest" not in inst:
            out.insert(0, {"id": want, "name": want, "installed": False, "size": (av.items.get(want) or {}).get("size") if av else None, "needed": True})
        return out

    def blocker(self, ctx, item=""):
        if item:
            return "" if self._state(ctx)["server"] else "server_off"
        return "" if ctx.plat == "win32" else "package_manager"

    def check(self, ctx):
        av = Avail()
        try:
            rel = ctx.http.get_json(GH_RELEASE.format(repo="ollama/ollama"))
        except NetworkError as exc:
            return _net_error(av, exc)
        av.latest = str(rel.get("tag_name", "")).lstrip("v")
        for a in rel.get("assets", []):
            if a.get("name") == "OllamaSetup.exe":
                av.ok, av.size, av.url, av.filename = True, int(a.get("size") or 0), a.get("browser_download_url", ""), "OllamaSetup.exe"
                d = str(a.get("digest", ""))
                if d.startswith("sha256:"):
                    av.expect = Expect(sha256=d[7:], size=av.size or 0)
        if ctx.plat != "win32":
            av.note, av.ok = "no_installer", False
        for name in {n for n, _ in SUGGESTED_MODELS} | ({self._wanted(ctx)} - {""}):
            sz = self._model_size(ctx, name)
            av.items[name] = {"size": sz}
        return av

    def _model_size(self, ctx: Ctx, name: str) -> Optional[int]:
        if not MODEL_RE.match(name):
            return None
        model, _, tag = name.partition(":")
        if "/" not in model:
            pass
        try:
            m = ctx.http.get_json(OLLAMA_MANIFEST.format(name=model, tag=tag or "latest"), limit=500_000)
            return int((m.get("config") or {}).get("size", 0)) + sum(int(x.get("size", 0)) for x in m.get("layers", []))
        except (NetworkError, ValueError, TypeError):
            return None

    def check_item(self, ctx, item):
        return {"size": self._model_size(ctx, item)}

    def plan(self, ctx, item, av):
        if not item:
            if not av.ok:
                raise ComponentError("not_checked")
            return Plan("Ollama " + av.latest, av.url, av.filename, av.expect, ctx.store.downloads(), is_installer=True)
        if not MODEL_RE.match(item):
            raise ComponentError("unknown_item")
        st = self._state(ctx)
        if not st["server"]:
            raise ComponentError("server_off")
        base = st["base"]

        def task(job: Job) -> None:
            if ctx.demo and getattr(ctx.demo, "active", False):
                return ctx.demo.pull(job, item)
            job.phase = "working"
            layers: dict[str, list[int]] = {}
            last_pub = 0.0
            try:
                with ollama_call(base, "/api/pull", "POST", {"model": item, "stream": True}, timeout=60) as r:
                    for raw in r:
                        if job.cancel.is_set():
                            return
                        try:
                            ev = json.loads(raw.decode())
                        except ValueError:
                            continue
                        if ev.get("error"):
                            raise JobFailed(f"O Ollama respondeu: {ev['error']}", "Confira o nome do modelo e a internet.")
                        if ev.get("total"):
                            layers[ev.get("digest", "x")] = [int(ev["total"]), int(ev.get("completed", 0))]
                            job.total = sum(v[0] for v in layers.values())
                            job.done = sum(v[1] for v in layers.values())
                            job.phase = "downloading"
                        else:
                            job.phase = "working"
                        now = time.time()
                        if job.publish and now - last_pub > 0.2:
                            last_pub = now
                            job.publish()
            except urllib.error.URLError as exc:
                raise JobFailed("Não consegui falar com o Ollama (ele está aberto?).", "Abra o Ollama e tente de novo.") from exc
        return Plan(f"Ollama · {item}", task=task)

    def removable(self, ctx, det, item=""):
        return bool(item) and any(m["name"] in (item, f"{item}:latest") for m in det.extra.get("models", []))

    def remove(self, ctx, item=""):
        if not MODEL_RE.match(item or ""):
            raise ComponentError("unknown_item")
        st = self._state(ctx)
        if not st["server"]:
            raise ComponentError("server_off")
        if ctx.demo and getattr(ctx.demo, "active", False):
            return ctx.demo.delete(item)
        try:
            with ollama_call(st["base"], "/api/delete", "DELETE", {"model": item}, timeout=15):
                pass
        except urllib.error.URLError as exc:
            raise ComponentError("remove_failed", str(exc)) from exc
        return {"removed": 1}

    def folder(self, ctx):
        return models_dir()

    def manual(self, ctx):
        return {"links": [("ollama.com/download", "https://ollama.com/download"),
                          ("Modelos", "https://ollama.com/library")],
                "commands": [("winget", "winget install -e --id Ollama.Ollama"), ("Baixar um modelo", "ollama pull llama3.2:3b"),
                             ("Linux", "curl -fsSL https://ollama.com/install.sh | sh")],
                "notes": ["ollama_note"]}


class GeminiComp(Component):
    id, category = "gemini", "ai"

    def detect(self, ctx):
        key = bool(ctx.usage().get("gemini_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        return Detect(key, "", "", extra={"key": key})

    def needed(self, ctx, det):
        u = ctx.usage()
        return bool(u.get("ai_enabled") and u.get("ai_provider") == "gemini" and not det.installed)

    def folder(self, ctx):
        return None

    def blocker(self, ctx, item=""):
        return "no_download"

    def manual(self, ctx):
        return {"links": [("Chave grátis (Google AI Studio)", "https://aistudio.google.com/apikey"),
                          ("Documentação do Gemini", "https://ai.google.dev/gemini-api/docs")],
                "commands": [], "notes": ["gemini_note"]}


ALL: list[Component] = [
    PythonComp(), TesseractComp(), TessdataComp(), RapidOcrComp(), EasyOcrComp(), PaddleComp(), WinOcrComp(), OpenCvComp(),
    ArgosComp(), OllamaComp(), GeminiComp(), GttsComp(), SpeechComp(),
]
