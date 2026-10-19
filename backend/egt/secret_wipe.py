"""'Remover chave': apaga um segredo do programa e procura restos dele no sistema.

Remove a stored API key and wipe traces: settings file (atomic rewrite + overwrite of the old copy, .tmp/.bak leftovers),
log files (redacted in place), any text/SQLite file of the config dir, backend memory. Optional: the user-level
environment variable on Windows (HKCU\\Environment) — never the system-level one (HKLM).
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from . import paths, vault
from .config import SECRET_PATHS, Settings, leftover_files

log = logging.getLogger(__name__)

ENV_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
REDACTED = "[chave removida]"
_TEXT_EXT = {".log", ".txt", ".json", ".csv", ".tmp", ".bak", ".old", ".1", ".2", ".3", ".4", ".5"}


def _needles(plain: str) -> list[bytes]:
    out = []
    if plain and len(plain) >= 8:
        out += [plain.encode("utf-8"), plain.encode("utf-16-le")]
    return out


def _scan_dir(root: Path, plain: str) -> list[Path]:
    """Arquivos (recursivo) da pasta de configuração que contêm a chave em texto puro (utf-8 ou utf-16)."""
    hits = []
    needles = _needles(plain)
    if not needles:
        return hits
    for f in root.rglob("*"):
        try:
            if not f.is_file() or f.stat().st_size > 64 * 1024 * 1024:
                continue
            data = f.read_bytes()
        except OSError:
            continue
        if any(n in data for n in needles):
            hits.append(f)
    return hits


def _redact_text_file(f: Path, plain: str) -> bool:
    try:
        data = f.read_bytes()
        new = data
        for n in _needles(plain):
            rep = REDACTED.encode("utf-16-le") if n == plain.encode("utf-16-le") else REDACTED.encode()
            new = new.replace(n, rep)
        if new == data:
            return False
        with open(f, "r+b") as fh:          # no lugar (o log continua aberto pelo programa)
            fh.write(new)
            fh.truncate()
            fh.flush()
            os.fsync(fh.fileno())
        return True
    except OSError:
        return False


def _redact_sqlite(f: Path, plain: str) -> bool:
    try:
        con = sqlite3.connect(str(f), timeout=5)
        try:
            changed = 0
            for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")') if (r[2] or "").upper() in ("", "TEXT")]
                for c in cols:
                    cur = con.execute(f'UPDATE "{table}" SET "{c}" = replace("{c}", ?, ?) WHERE instr("{c}", ?) > 0',
                                      (plain, REDACTED, plain))
                    changed += cur.rowcount or 0
            con.commit()
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.execute("VACUUM")
            return changed > 0
        finally:
            con.close()
    except sqlite3.Error:
        return False


def remove_secret(settings: Settings, path: str, root: Optional[Path] = None) -> dict:
    """Apaga o segredo `path` e os restos dele. Retorna um relatório sem nenhum segredo."""
    if path not in SECRET_PATHS:
        raise KeyError(path)
    root = Path(root) if root else settings.path.parent
    blob = settings.get(path)
    plain = settings.secret(path)                   # só para procurar restos (se ainda abrir neste PC)
    had = vault.is_blob(blob) or bool(isinstance(blob, str) and blob)
    settings.set_secret(path, "", wipe=True)        # grava sem o segredo, sobrescreve a cópia antiga, apaga .tmp/.bak
    report = {"path": path, "had_key": had, "settings_rewritten": True, "leftovers_removed": [], "redacted": [],
              "still_found": []}
    for extra in leftover_files(settings.path):     # (set_secret já limpou; confere de novo)
        try:
            extra.unlink()
            report["leftovers_removed"].append(extra.name)
        except OSError:
            pass
    if plain:
        for f in _scan_dir(root, plain):
            ok = _redact_sqlite(f, plain) if f.suffix.lower() in (".sqlite3", ".sqlite", ".db") else _redact_text_file(f, plain)
            if ok:
                report["redacted"].append(str(f.relative_to(root)) if f.is_relative_to(root) else f.name)
        # sobra em outros lugares? (ex.: -wal do SQLite que ainda não foi integrado)
        report["still_found"] = [f.name for f in _scan_dir(root, plain)]
        lf = paths.log_file()
        if not lf.is_relative_to(root):
            for f in [lf, *lf.parent.glob(lf.name + ".*")]:
                if _redact_text_file(f, plain):
                    report["redacted"].append(f.name)
    plain = ""  # noqa: F841  (strings do Python não podem ser zeradas; a referência sai de escopo aqui)
    log.info("chave removida: %s (restos limpos: %d)", path, len(report["redacted"]))
    return report


# ------------------------------------------------------------------ variáveis de ambiente
def _reg_value(hive, subkey: str, name: str) -> bool:
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(hive, subkey) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return bool(v)
    except OSError:
        return False


USER_ENV = "Environment"
SYSTEM_ENV = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def env_status() -> list[dict]:
    """[{name, process, user, system}] — onde cada variável de chave existe (sem o valor)."""
    out = []
    for n in ENV_NAMES:
        st = {"name": n, "process": bool(os.environ.get(n)), "user": False, "system": False}
        if sys.platform == "win32":
            import winreg  # type: ignore
            st["user"] = _reg_value(winreg.HKEY_CURRENT_USER, USER_ENV, n)
            st["system"] = _reg_value(winreg.HKEY_LOCAL_MACHINE, SYSTEM_ENV, n)
        if st["process"] or st["user"] or st["system"]:
            out.append(st)
    return out


def _broadcast_env_change() -> None:
    if sys.platform != "win32":
        return
    import ctypes
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
    res = ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",  # type: ignore[attr-defined]
                                             SMTO_ABORTIFHUNG, 5000, ctypes.byref(res))


def remove_user_env(name: str) -> dict:
    """Remove a variável do USUÁRIO (HKCU\\Environment) e da memória deste processo. Nunca mexe na do sistema (HKLM)."""
    if name not in ENV_NAMES:
        raise KeyError(name)
    removed_user = False
    if sys.platform == "win32":
        import winreg  # type: ignore
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, USER_ENV, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
                removed_user = True
        except FileNotFoundError:
            pass
        if removed_user:
            _broadcast_env_change()
    os.environ.pop(name, None)                    # este processo para de usar na hora
    system = any(s["name"] == name and s["system"] for s in env_status())
    return {"name": name, "removed_user": removed_user, "system_level": system,
            "platform": sys.platform}


