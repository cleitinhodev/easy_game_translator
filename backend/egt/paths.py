"""Caminhos do projeto e da pasta de configuração do usuário (sem dependências extras).

Project/asset paths and per-user config dir (no extra deps).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIRNAME = "EasyGameTranslator"


def project_root() -> Path:
    """Raiz do projeto (ou pasta temporária do PyInstaller). / Project root."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def asset(*parts: str) -> Path:
    """Caminho absoluto de um arquivo em assets/. / Absolute path inside assets/."""
    return project_root().joinpath("assets", *parts)


def config_dir() -> Path:
    """Pasta de configuração do usuário (criada se não existir).

    Windows: %APPDATA%/EasyGameTranslator · outros: $XDG_CONFIG_HOME ou ~/.config.
    Pode ser forçada com EGT_CONFIG_DIR (útil em testes).
    """
    override = os.environ.get("EGT_CONFIG_DIR")
    if override:
        base = Path(override)
    elif os.name == "nt":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        base = Path(appdata) / APP_DIRNAME
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        base = Path(xdg) / APP_DIRNAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_file() -> Path:
    return config_dir() / "settings.json"


def glossary_file() -> Path:
    return config_dir() / "glossary.json"


def database_file() -> Path:
    return config_dir() / "egt.sqlite3"


def profiles_dir() -> Path:
    d = config_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = config_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return logs_dir() / "egt.log"
