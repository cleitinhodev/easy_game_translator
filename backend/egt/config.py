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

from . import paths, vault

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
        # ordem da cadeia de reserva e motores ligados (catálogo em translate/providers.py)
        "order": ["google", "bing", "mymemory", "mozhi", "yandex", "apertium", "libre", "deepl", "microsoft",
                  "gcloud", "baidu", "youdao", "niutrans", "argos"],
        "enabled": ["google", "bing", "mymemory"],
        "cache_only": False,
        "mymemory_email": "",       # CIFRADO (opcional: aumenta a cota grátis)
        "mozhi_url": "",            # "" = alterna entre as instâncias públicas conhecidas
        "mozhi_engine": "duckduckgo",
        "apertium_url": "https://apertium.org/apy",
        "libre_url": "",            # servidor próprio (ex.: http://localhost:5000) ou https://libretranslate.com com chave
        "libre_key": "",            # CIFRADO
        "deepl_key": "",            # CIFRADO
        "microsoft_key": "",        # CIFRADO (Azure AI Translator)
        "microsoft_region": "",
        "gcloud_key": "",           # CIFRADO
        "baidu_appid": "",
        "baidu_key": "",            # CIFRADO
        "youdao_appkey": "",
        "youdao_secret": "",        # CIFRADO
        "niutrans_key": "",         # CIFRADO
        "timeout": 8.0,
    },
    "ai": {                          # OPCIONAL — desligado por padrão
        "mode": "off",              # 'off' | 'gemini' | 'ollama' — SÓ a IA escolhida entra na cadeia de tradução
        "gemini_key": "",           # guardada CIFRADA ({"enc": ...}, ver vault.py); "" = sem chave
        "gemini_model": "gemini-3.5-flash-lite",
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


REMOVED_ENGINES = {"lingva": "mozhi"}          # 4.0.8: o Lingva parou (instâncias mortas ou devolvendo o texto sem traduzir)


def _migrate_translation(tr: dict, raw: dict) -> bool:
    """Ajustes de versões antigas na seção translation. Devolve True se mudou algo."""
    changed = False
    for lst in ("order", "enabled"):
        v = tr.get(lst)
        if isinstance(v, list) and any(e in REMOVED_ENGINES for e in v):
            new = []
            for e in v:
                e = REMOVED_ENGINES.get(e, e)
                if e not in new:
                    new.append(e)
            tr[lst] = new
            changed = True
    if raw.get("libre_url") == "http://localhost:5000" and "libre_url" in raw and not raw.get("libre_key") \
            and "libre" not in (tr.get("enabled") or []):
        tr["libre_url"] = ""                       # antigo padrão (servidor local que quase ninguém tinha)
        changed = True
    if "lingva_url" in raw:
        changed = True                             # a chave some do arquivo no próximo salvamento
    return changed


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
            raw = None
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data = _merge(DEFAULTS, raw)
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:
                log.warning("settings.json inválido, usando padrões: %s", exc)
            self._sanitize()
            dirty = False
            if isinstance(raw, dict):
                rai = raw.get("ai") if isinstance(raw.get("ai"), dict) else {}
                if rai and "mode" not in rai:        # 4.0.5 e antes: ai.enabled + ai.provider → ai.mode
                    prov = rai.get("provider") if rai.get("provider") in ("gemini", "ollama") else "gemini"
                    self.data["ai"]["mode"] = prov if rai.get("enabled") else "off"
                    dirty = True
                rtr = raw.get("translation") if isinstance(raw.get("translation"), dict) else {}
                if rtr and _migrate_translation(self.data["translation"], rtr):   # 4.0.8: Lingva → Mozhi etc.
                    dirty = True
            plain_found = False
            for p in SECRET_PATHS:                   # chave em texto puro (versões antigas) → cifra e apaga o texto puro
                v = self.get(p)
                if isinstance(v, str) and v.strip():
                    try:
                        self.set(p, vault.protect(v.strip(), p, self.path.parent), save=False)
                        plain_found = dirty = True
                    except Exception as exc:  # noqa: BLE001
                        log.error("não foi possível cifrar %s: %s", p, type(exc).__name__)
                elif not (v == "" or vault.is_blob(v)):
                    self.set(p, "", save=False)
                    dirty = True
            if dirty:
                self.save(wipe=plain_found)
                if plain_found:
                    log.info("chaves de API migradas para o formato cifrado")

    def save(self, wipe: bool = False) -> None:
        """Gravação atômica (arquivo temporário + replace). wipe=True: antes, sobrescreve o arquivo antigo com zeros
        (melhor esforço — SSD/sistema de arquivos podem manter cópias) e apaga sobras .tmp/.bak."""
        with self._lock:
            self._sanitize()
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
                if os.name != "nt":
                    try:
                        os.chmod(tmp, 0o600)
                    except OSError:
                        pass
                if wipe:
                    _overwrite(self.path)
                tmp.replace(self.path)
                if wipe:
                    for extra in leftover_files(self.path):
                        _overwrite(extra)
                        try:
                            extra.unlink()
                        except OSError:
                            pass
            except OSError as exc:
                log.error("não foi possível salvar settings: %s", exc)

    # -- segredos (cifrados em disco; texto puro só na hora do uso)
    def secret(self, path: str) -> str:
        """Texto puro do segredo, ou "" se não houver/se não puder ser aberto neste PC."""
        v = self.get(path)
        if isinstance(v, str):
            return v.strip()        # só sobra texto puro se a cifragem falhou na migração (o valor continua valendo)
        if not vault.is_blob(v):
            return ""
        try:
            return vault.unprotect(v, self.path.parent)
        except vault.VaultError:
            return ""

    def secret_state(self, path: str) -> str:
        """'none' | 'ok' | 'unreadable' (cifrada em outro PC/usuário ou adulterada)."""
        v = self.get(path)
        if isinstance(v, str):
            return "ok" if v.strip() else "none"
        if not vault.is_blob(v):
            return "none"
        try:
            vault.unprotect(v, self.path.parent)
            return "ok"
        except vault.VaultError:
            return "unreadable"

    def set_secret(self, path: str, plain: str, wipe: bool = False) -> None:
        if path not in SECRET_PATHS:
            raise KeyError(path)
        old = self.get(path)
        plain = (plain or "").strip()
        self.set(path, vault.protect(plain, path, self.path.parent) if plain else "", save=False)
        if vault.is_blob(old):
            vault.forget(old)
        self.save(wipe=wipe or not plain)

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
        if self.data["ai"].get("mode") not in ("off", "gemini", "ollama"):
            self.data["ai"]["mode"] = "off"
        if not isinstance(self.data["ai"].get("gemini_model"), str) or not self.data["ai"]["gemini_model"].strip():
            self.data["ai"]["gemini_model"] = DEFAULTS["ai"]["gemini_model"]
        if self.data["ui"].get("material") not in ("auto", "mica", "acrylic", "none"):
            self.data["ui"]["material"] = "auto"
        if self.data["ui"].get("reduce_motion") not in ("system", "on", "off"):
            self.data["ui"]["reduce_motion"] = "system"
        tr = self.data["translation"]
        for lst in ("order", "enabled"):
            v = tr.get(lst)
            tr[lst] = [e for e in v if isinstance(e, str) and e] if isinstance(v, list) else list(DEFAULTS["translation"][lst])
        if tr.get("mozhi_engine") not in ("duckduckgo", "yandex", "google"):
            tr["mozhi_engine"] = "duckduckgo"
        try:
            tr["timeout"] = round(_clamp(float(tr.get("timeout", 8.0)), 2.0, 30.0), 1)
        except (TypeError, ValueError):
            tr["timeout"] = 8.0
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
        return (self.secret("ai.gemini_key") or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY") or "").strip()


def _overwrite(p: Path) -> None:
    """Melhor esforço: sobrescreve o conteúdo com zeros antes de substituir/apagar."""
    try:
        n = p.stat().st_size
        if n:
            with open(p, "r+b") as fh:
                fh.write(b"\0" * n)
                fh.flush()
                os.fsync(fh.fileno())
    except OSError:
        pass


def leftover_files(settings_path: Path) -> list[Path]:
    """Cópias que poderiam guardar texto antigo: settings.tmp, settings.json.bak, settings.json~, settings*.old…"""
    d, stem, name = settings_path.parent, settings_path.stem, settings_path.name
    out = []
    try:
        for f in d.iterdir():
            if f == settings_path or not f.is_file():
                continue
            if f.name.startswith((stem + ".", name)) and f.suffix.lower() in (".tmp", ".bak", ".old", ".orig", ".swp") \
                    or f.name in (name + "~",):
                out.append(f)
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- API (v4)
# todos os campos sensíveis (chaves e o e-mail do MyMemory) — cifrados em disco, mascarados na interface
SECRET_PATHS = ("translation.mymemory_email", "translation.libre_key", "translation.deepl_key",
                "translation.microsoft_key", "translation.gcloud_key", "translation.baidu_key",
                "translation.youdao_secret", "translation.niutrans_key", "ai.gemini_key")
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
    states = {}
    for p in SECRET_PATHS:
        sec, key = p.split(".")
        st = settings.secret_state(p)
        states[p] = st
        data[sec][key] = MASK if st == "ok" else ""      # nunca devolve a chave (nem o blob cifrado)
    data["secrets"] = {"state": states, "scheme": vault.scheme(settings.path.parent)}
    data["ai"]["env_key_found"] = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    data["ai"]["env_key_names"] = [n for n in ("GEMINI_API_KEY", "GOOGLE_API_KEY") if os.environ.get(n)]
    data["config_path"] = str(settings.path)
    return data


def apply_changes(settings: "Settings", changes: dict[str, Any]) -> list[str]:
    """Aplica {'a.b': valor}. Ignora caminhos desconhecidos e máscaras. Retorna os caminhos alterados."""
    changed = []
    secrets_changed: list[tuple[str, str]] = []
    for path, value in changes.items():
        if path not in EDITABLE_PATHS:
            raise KeyError(path)
        if path in SECRET_PATHS:
            if value == MASK:
                continue
            if not isinstance(value, str):
                raise ValueError(f"{path}: esperado texto")
            secrets_changed.append((path, value))
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
    for path, value in secrets_changed:
        settings.set_secret(path, value)
        changed.append(path)
    return changed
