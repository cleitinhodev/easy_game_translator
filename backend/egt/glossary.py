"""Regras de substituição (corrigir erros do OCR) e glossário de nomes a não traduzir.

Replace rules (fix recurring OCR errors) and keep-untranslated names glossary.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Optional

from . import paths

log = logging.getLogger(__name__)

_PH_RE = re.compile(r"XQ([0-9A-F]{6})QX")


def _ph(term: str) -> str:
    h = hashlib.md5(term.casefold().encode("utf-8")).hexdigest()[:6].upper()
    return f"XQ{h}QX"


class Glossary:
    """rules: [{'find','replace','regex','case','enabled'}] · keep: [termos]."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._lock = threading.RLock()
        self.rules: list[dict] = []
        self.keep: list[str] = []
        self._compiled: list[tuple[re.Pattern, str, bool]] = []
        self._keep_re: Optional[re.Pattern] = None
        self._keep_map: dict[str, str] = {}
        if self.path:
            self.load()
        else:
            self._rebuild()

    # ---------------------------------------------------------------- io
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
            self.set_data(raw.get("rules", []), raw.get("keep", []), save=False)
        except FileNotFoundError:
            self._rebuild()
        except (OSError, ValueError, AttributeError) as exc:
            log.warning("glossary.json inválido: %s", exc)
            self._rebuild()

    def save(self) -> None:
        if not self.path:
            return
        with self._lock:
            try:
                self.path.write_text(json.dumps({"rules": self.rules, "keep": self.keep},
                                                ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                log.error("não foi possível salvar glossário: %s", exc)

    def set_data(self, rules: list[dict], keep: list[str], save: bool = True) -> None:
        with self._lock:
            clean = []
            for r in rules:
                find = str(r.get("find", ""))
                if not find:
                    continue
                clean.append({"find": find, "replace": str(r.get("replace", "")),
                              "regex": bool(r.get("regex", False)),
                              "case": bool(r.get("case", False)),
                              "enabled": bool(r.get("enabled", True))})
            self.rules = clean
            seen, kept = set(), []
            for t in keep:
                t = str(t).strip()
                if t and t.casefold() not in seen:
                    seen.add(t.casefold())
                    kept.append(t)
            self.keep = kept
            self._rebuild()
            if save:
                self.save()

    def _rebuild(self) -> None:
        comp = []
        for r in self.rules:
            if not r["enabled"]:
                continue
            flags = 0 if r["case"] else re.IGNORECASE
            try:
                pat = re.compile(r["find"] if r["regex"] else re.escape(r["find"]), flags)
            except re.error as exc:
                log.warning("regex inválida %r: %s", r["find"], exc)
                continue
            comp.append((pat, r["replace"], r["regex"]))
        self._compiled = comp
        terms = sorted(self.keep, key=len, reverse=True)
        self._keep_map = {_ph(t)[2:-2]: t for t in terms}
        self._keep_re = (re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
                         if terms else None)

    # ------------------------------------------------------------- uso
    def apply_replacements(self, text: str) -> str:
        """Aplica as regras de substituição ao texto do OCR (antes de traduzir)."""
        with self._lock:
            for pat, repl, is_regex in self._compiled:
                try:
                    text = pat.sub(repl, text) if is_regex else pat.sub(lambda _m, r=repl: r, text)
                except (re.error, IndexError) as exc:
                    log.debug("regra falhou: %s", exc)
            return text

    def protect(self, text: str) -> tuple[str, dict[str, str]]:
        """Troca nomes do glossário por marcadores estáveis (não traduzidos)."""
        with self._lock:
            if not self._keep_re:
                return text, {}
            mapping: dict[str, str] = {}

            def sub(m: re.Match) -> str:
                ph = _ph(m.group(0))
                mapping[ph] = m.group(0)  # preserva a grafia do texto original
                return ph

            return self._keep_re.sub(sub, text), mapping

    def restore(self, text: str, mapping: Optional[dict[str, str]] = None) -> str:
        """Devolve os nomes originais no texto traduzido."""
        if not text:
            return text
        with self._lock:
            mapping = mapping or {}

            def sub(m: re.Match) -> str:
                ph = m.group(0)
                return mapping.get(ph) or self._keep_map.get(m.group(1), ph)

            return _PH_RE.sub(sub, text)


def default_glossary() -> Glossary:
    return Glossary(paths.glossary_file())
