"""Pasta de componentes do usuário (gravável) e configuração de locais.

Tudo que o app baixa/instala fica aqui — nunca dentro da instalação (pasta do .exe). O arquivo
`components.json` fica na pasta de configuração do usuário (fora do repositório) e guarda a raiz escolhida
e pastas personalizadas por componente.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from .. import paths

log = logging.getLogger(__name__)

# subpasta padrão de cada componente dentro da raiz
DEFAULT_SUB: dict[str, str] = {
    "python": "downloads",
    "tesseract": "tesseract",
    "tessdata": "tessdata",
    "rapidocr": "models/rapidocr",
    "easyocr": "models/easyocr",
    "paddleocr": "models/paddleocr",
    "winocr": "downloads",
    "opencv": "site-packages",
    "argos": "argos",
    "ollama": "ollama",
    "gemini": "downloads",
    "gtts": "site-packages",
    "speechrecognition": "site-packages",
}
SHARED_SUBS = ("site-packages", "downloads")        # compartilhadas: o botão Remover não apaga a pasta inteira


class ComponentsStore:
    def __init__(self, cfg_file: Optional[Path] = None):
        self.file = Path(cfg_file) if cfg_file else paths.config_dir() / "components.json"
        self._lock = threading.RLock()
        self.data: dict[str, Any] = {"root": "", "dirs": {}}
        self.load()

    # -- io
    def load(self) -> None:
        with self._lock:
            try:
                raw = json.loads(self.file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data["root"] = str(raw.get("root") or "")
                    d = raw.get("dirs")
                    self.data["dirs"] = {str(k): str(v) for k, v in d.items()} if isinstance(d, dict) else {}
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:
                log.warning("components.json inválido, usando padrões: %s", exc)

    def save(self) -> None:
        with self._lock:
            try:
                self.file.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.file.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(self.file)
            except OSError as exc:
                log.error("não foi possível salvar components.json: %s", exc)

    # -- locais
    def default_root(self) -> Path:
        return paths.config_dir() / "components"

    def root(self) -> Path:
        r = self.data.get("root") or ""
        return Path(r) if r else self.default_root()

    def dir_for(self, comp_id: str) -> Path:
        custom = self.data["dirs"].get(comp_id)
        if custom:
            return Path(custom)
        sub = DEFAULT_SUB.get(comp_id)
        if sub is None:
            raise KeyError(comp_id)
        return self.root().joinpath(*sub.split("/"))

    def site_packages(self) -> Path:
        return self.root() / "site-packages"

    def downloads(self) -> Path:
        return self.root() / "downloads"

    def tessdata_dir(self) -> Path:
        return self.dir_for("tessdata")

    def ensure(self, comp_id: str) -> Path:
        d = self.dir_for(comp_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def allowed_dirs(self) -> list[Path]:
        out = {self.root(), self.site_packages(), self.downloads()}
        for cid in DEFAULT_SUB:
            out.add(self.dir_for(cid))
        return sorted(out, key=str)

    def is_allowed(self, p: str | Path) -> bool:
        """O caminho (resolvido) está dentro de alguma pasta de componente registrada? (anti path-traversal)"""
        try:
            rp = Path(p).resolve()
        except (OSError, RuntimeError, ValueError):
            return False
        for d in self.allowed_dirs():
            try:
                rd = d.resolve()
            except (OSError, RuntimeError):
                continue
            if rp == rd or rd in rp.parents:
                return True
        return False

    # -- escolher locais
    def set_root(self, path: str, copy_existing: bool = False) -> dict:
        res = validate_dir(path)
        if not res["ok"]:
            return res
        new = Path(path).expanduser()
        old = self.root()
        res["copied"] = 0
        if copy_existing and old.exists() and old.resolve() != new.resolve():
            res["copied"] = copy_tree(old, new)
        with self._lock:
            self.data["root"] = str(new)
            self.save()
        new.mkdir(parents=True, exist_ok=True)
        return res

    def set_dir(self, comp_id: str, path: str, copy_existing: bool = False) -> dict:
        if comp_id not in DEFAULT_SUB:
            raise KeyError(comp_id)
        res = validate_dir(path)
        if not res["ok"]:
            return res
        new = Path(path).expanduser()
        old = self.dir_for(comp_id)
        res["copied"] = 0
        if copy_existing and old.exists() and old.resolve() != new.resolve():
            res["copied"] = copy_tree(old, new)
        with self._lock:
            self.data["dirs"][comp_id] = str(new)
            self.save()
        new.mkdir(parents=True, exist_ok=True)
        return res

    def reset_dir(self, comp_id: str) -> None:
        with self._lock:
            self.data["dirs"].pop(comp_id, None)
            self.save()


def copy_tree(src: Path, dst: Path) -> int:
    """Copia (nunca apaga o original). Devolve a quantidade de arquivos copiados."""
    n = 0
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.rglob("*"):
        if f.is_file():
            t = dst / f.relative_to(src)
            if t.exists():
                continue
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)
            n += 1
    return n


def validate_dir(path: str, need_bytes: int = 0) -> dict:
    """Valida uma pasta escolhida pelo usuário: gravável, espaço livre, avisos de caminho problemático."""
    out: dict[str, Any] = {"ok": False, "path": path, "errors": [], "warnings": [], "free": 0}
    if not path or not isinstance(path, str) or "\x00" in path:
        out["errors"].append("caminho vazio ou inválido")
        return out
    p = Path(path).expanduser()
    if not p.is_absolute():
        out["errors"].append("use um caminho absoluto")
        return out
    if p.parent == p:
        out["errors"].append("escolha uma pasta, não a raiz do disco")
        return out
    low = str(p).lower().replace("/", "\\")
    if "\\program files" in low or "\\windows\\" in low or low.endswith("\\windows"):
        out["warnings"].append("pasta dentro de Program Files/Windows: normalmente exige administrador e pode falhar")
    if not str(p).isascii():
        out["warnings"].append("o caminho tem caracteres não-ASCII (acentos etc.): alguns motores (Tesseract, modelos) podem falhar")
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / f".egt_write_test_{os.getpid()}"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        out["errors"].append(f"sem permissão de escrita: {exc.strerror or exc}")
        return out
    try:
        out["free"] = shutil.disk_usage(p).free
    except OSError:
        out["free"] = 0
    if need_bytes and out["free"] and out["free"] < need_bytes:
        out["errors"].append("espaço livre insuficiente")
        return out
    if out["free"] and out["free"] < 200 * 1024 * 1024:
        out["warnings"].append("pouco espaço livre (menos de 200 MB)")
    out["ok"] = True
    return out


# ---------------------------------------------------------------- ambiente
_applied: dict[str, Any] = {"sp": None}


def setup_environment(store: ComponentsStore) -> dict:
    """Chamado na partida do backend: cria as pastas e põe `site-packages` no FIM do sys.path.

    No fim de propósito: o que vem embutido no executável sempre tem prioridade; a pasta do usuário só
    completa o que falta (nunca substitui/quebra a instalação).
    """
    info: dict[str, Any] = {"root": str(store.root()), "site_packages": str(store.site_packages())}
    try:
        for sub in ("site-packages", "downloads", "tessdata", "tesseract", "models", "argos"):
            (store.root() / sub).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("não consegui criar a pasta de componentes: %s", exc)
        info["error"] = str(exc)
        return info
    sp = str(store.site_packages())
    old = _applied.get("sp")
    if old and old != sp and old in sys.path:
        sys.path.remove(old)
    if sp not in sys.path:
        sys.path.append(sp)
    _applied["sp"] = sp
    import importlib
    importlib.invalidate_caches()
    # DLLs nativas (Windows) dos pacotes instalados na pasta do usuário
    if hasattr(os, "add_dll_directory"):
        for cand in (store.site_packages(), store.site_packages() / "bin"):
            try:
                if cand.is_dir():
                    os.add_dll_directory(str(cand))
            except OSError:
                pass
    ed = store.dir_for("easyocr")
    os.environ.setdefault("EGT_EASYOCR_DIR", str(ed))
    return info


def user_tessdata(store: Optional[ComponentsStore]) -> Optional[Path]:
    """Pasta tessdata do usuário se tiver ao menos um .traineddata."""
    if store is None:
        return None
    d = store.tessdata_dir()
    try:
        if d.is_dir() and any(d.glob("*.traineddata")):
            return d
    except OSError:
        pass
    return None


# instância global (a mesma usada pelo servidor); trocável em testes
_global: dict[str, ComponentsStore] = {}


def get_store() -> ComponentsStore:
    s = _global.get("s")
    if s is None:
        s = _global["s"] = ComponentsStore()
    return s


def set_store(s: Optional[ComponentsStore]) -> None:
    if s is None:
        _global.pop("s", None)
    else:
        _global["s"] = s
