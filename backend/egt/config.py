"""Configurações do usuário (JSON na pasta de configuração, nunca dentro do projeto).

User settings (JSON in the user config dir, never inside the project).
Chaves de API: variável de ambiente ou este arquivo — nunca no código.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

from . import paths

log = logging.getLogger(__name__)

LANG_CODE_RE = re.compile(r"[a-z]{2,3}(-[A-Za-z]{2,4})?")

DEFAULTS: dict[str, Any] = {
    "ui": {
        "language": "auto",         # 'auto' (idioma do sistema) ou código do idioma da interface (pt-BR, en, es, ja, zh-CN…)
        "play_intro": True,
        "intro_full": True,
        "always_on_top": False,
        "font_size": 16,
        "clear_on_empty": False,
        "material": "auto",         # Windows 11: 'auto' | 'mica' | 'acrylic' | 'none'
        "close_to_tray": True,      # fechar a janela minimiza para a bandeja
        "reduce_motion": "system",  # 'system' | 'on' | 'off'
        "typewriter": True,         # efeito de digitação nas traduções novas
    },
    "capture": {
        "interval": 1.0,            # segundos (0.2–5)
    },
    "filters": {
        "stable_ms": 450,           # espera o texto parar de mudar (efeito de digitação)
        "max_wait_ms": 4000,
        "min_chars": 3,
        "min_alnum_ratio": 0.5,
        "min_confidence": 35,
        "diff_mean": 1.0,           # sensibilidade da detecção de mudança de imagem
        "similarity": 0.96,
    },
    "ocr": {
        "engine": "tesseract",
        "tesseract_path": "",
        "tesseract_psm": 6,
        "easyocr_gpu": False,
    },
    "translation": {
        "order": ["google", "mymemory", "libre", "lingva", "microsoft", "argos"],
        "enabled": ["google", "mymemory"],
        "cache_only": False,
        "libre_url": "http://localhost:5000",
        "libre_key": "",
        "lingva_url": "https://lingva.ml",
        "microsoft_key": "",
        "microsoft_region": "",
        "timeout": 8.0,
    },
    "ai": {                          # OPCIONAL — desligado por padrão
        "enabled": False,
        "provider": "gemini",       # 'gemini' | 'ollama'
        "gemini_key": "",           # prefira a variável GEMINI_API_KEY
        "gemini_model": "gemini-2.5-flash",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "llama3.2",
        "context": "",              # ex.: "RPG medieval; personagens: Nina, Kael"
    },
    "box": {
        "alpha": 0.92,
        "borderless": False,
        "click_through": False,
        "auto_font": True,
        "font_size": 15,
        "text_color": "#F2F2F2",
        "bg_color": "#14173a",
        "show_original": False,
        "exclude_from_capture": True,   # Windows 10 2004+: evita o OCR ler a própria caixa
    },
    "hotkeys": {
        "enabled": True,
        "toggle": "CommandOrControl+Alt+S",
        "translate_now": "CommandOrControl+Alt+T",
        "toggle_box": "CommandOrControl+Alt+B",
    },
    "last_profile": "",
}


def to_accelerator(combo: str) -> str:
    """Converte '<ctrl>+<alt>+s' (v3/pynput) para o formato do Electron: 'Control+Alt+S'."""
    if "<" not in combo:
        return combo
    names = {"ctrl": "Control", "control": "Control", "alt": "Alt", "shift": "Shift", "cmd": "Super",
             "win": "Super", "esc": "Escape", "enter": "Return"}
    out = []
    for part in combo.split("+"):
        p = part.strip().strip("<>").lower()
        out.append(names.get(p, p.upper() if len(p) == 1 else p.capitalize()))
    return "+".join(out)


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif k in out:
            out[k] = v
    return out


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class Settings:
    """Dicionário aninhado com acesso 'a.b.c', salvamento atômico e thread-safe."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else paths.settings_file()
        self._lock = threading.RLock()
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    # -- io
    def load(self) -> None:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data = _merge(DEFAULTS, raw)
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:
                log.warning("settings.json inválido, usando padrões: %s", exc)
            self._sanitize()

    def save(self) -> None:
        with self._lock:
            self._sanitize()
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
                if os.name != "nt":
                    try:
                        os.chmod(tmp, 0o600)  # pode conter chaves de API
                    except OSError:
                        pass
                tmp.replace(self.path)
            except OSError as exc:
                log.error("não foi possível salvar settings: %s", exc)

    def _sanitize(self) -> None:
        d = self.data
        try:
            d["capture"]["interval"] = round(_clamp(float(d["capture"].get("interval", 1.0)), 0.2, 5.0), 2)
            f = d["filters"]
            f["stable_ms"] = int(_clamp(f.get("stable_ms", 450), 0, 5000))
            f["min_chars"] = int(_clamp(f.get("min_chars", 3), 1, 50))
            f["min_confidence"] = int(_clamp(f.get("min_confidence", 35), 0, 95))
            d["box"]["alpha"] = _clamp(float(d["box"].get("alpha", 0.95)), 0.2, 1.0)
        except (TypeError, ValueError):
            self.data = copy.deepcopy(DEFAULTS)
        lang = self.data["ui"].get("language")
        if not (isinstance(lang, str) and (lang == "auto" or LANG_CODE_RE.fullmatch(lang))):
            self.data["ui"]["language"] = "auto"      # só 'auto' ou um código simples (a lista real fica no front-end)
        if self.data["ui"].get("material") not in ("auto", "mica", "acrylic", "none"):
            self.data["ui"]["material"] = "auto"
        if self.data["ui"].get("reduce_motion") not in ("system", "on", "off"):
            self.data["ui"]["reduce_motion"] = "system"
        hk = self.data.get("hotkeys", {})
        for k, v in list(hk.items()):
            if isinstance(v, str):
                hk[k] = to_accelerator(v)

    # -- acesso
    def get(self, path: str, default: Any = None) -> Any:
        with self._lock:
            cur: Any = self.data
            for part in path.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    return default
                cur = cur[part]
            return cur

    def set(self, path: str, value: Any, save: bool = True) -> None:
        with self._lock:
            parts = path.split(".")
            cur = self.data
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            cur[parts[-1]] = value
            if save:
                self.save()

    def section_all(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.data)

    def section(self, name: str) -> dict:
        with self._lock:
            return copy.deepcopy(self.data.get(name, {}))

    # -- chaves de API (nunca escritas em log)
    def gemini_key(self) -> str:
        return (self.get("ai.gemini_key", "") or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY") or "").strip()


# ---------------------------------------------------------------- API (v4)
SECRET_PATHS = ("translation.libre_key", "translation.microsoft_key", "ai.gemini_key")
MASK = "••••••••"
_EDITABLE_SECTIONS = ("ui", "capture", "filters", "ocr", "translation", "ai", "box", "hotkeys")


def _leaf_paths(d: dict, prefix: str = "") -> list[str]:
    out = []
    for k, v in d.items():
        p = f"{prefix}{k}"
        if isinstance(v, dict):
            out += _leaf_paths(v, p + ".")
        else:
            out.append(p)
    return out


EDITABLE_PATHS = frozenset(p for p in _leaf_paths(DEFAULTS) if p.split(".")[0] in _EDITABLE_SECTIONS)


def public_view(settings: "Settings") -> dict:
    """Cópia das configurações para a UI: chaves secretas viram máscara (ou vazio se não definidas)."""
    data = settings.section_all()
    for p in SECRET_PATHS:
        sec, key = p.split(".")
        data[sec][key] = MASK if data[sec].get(key) else ""
    data["ai"]["env_key_found"] = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    data["config_path"] = str(settings.path)
    return data


def apply_changes(settings: "Settings", changes: dict[str, Any]) -> list[str]:
    """Aplica {'a.b': valor}. Ignora caminhos desconhecidos e máscaras. Retorna os caminhos alterados."""
    changed = []
    for path, value in changes.items():
        if path not in EDITABLE_PATHS:
            raise KeyError(path)
        if path in SECRET_PATHS and value == MASK:
            continue
        ref = settings.get(path)
        if isinstance(ref, bool) and not isinstance(value, bool):
            raise ValueError(f"{path}: esperado booleano")
        if isinstance(ref, (int, float)) and not isinstance(ref, bool) and (
                isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError(f"{path}: esperado número")
        if isinstance(ref, str) and not isinstance(value, str):
            raise ValueError(f"{path}: esperado texto")
        if isinstance(ref, list) and not isinstance(value, list):
            raise ValueError(f"{path}: esperado lista")
        settings.set(path, value, save=False)
        changed.append(path)
    if changed:
        settings.save()
    return changed
