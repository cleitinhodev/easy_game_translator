"""Perfis por jogo (JSON na pasta de configuração) e sessão automática.

Per-game profiles: regions, OCR engine, alphabet, target language, preprocessing, interval, box geometry.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import paths
from .capture.screen import normalize_bbox
from .languages import ALPHABETS, DEFAULT_ALPHABET, LANG_NAMES, NAME_TO_CODE
from .preprocess import PreprocessOptions

log = logging.getLogger(__name__)

LAST_SESSION = "_last_session"


def _bbox(v: Any) -> Optional[list[int]]:
    b = normalize_bbox(v) if v else None
    return list(b) if b else None


@dataclass
class Profile:
    name: str = "Padrão"
    mode: str = "single"                 # 'single' | 'dual'
    region_single: Optional[list[int]] = None
    region_a: Optional[list[int]] = None
    region_b: Optional[list[int]] = None
    ocr_engine: str = "tesseract"
    alphabet: str = DEFAULT_ALPHABET
    target: str = "pt"
    interval: float = 1.0
    preprocess: PreprocessOptions = field(default_factory=PreprocessOptions)
    font_size: int = 16
    font_family: str = "default"         # id da família de fonte do texto traduzido (lista no front-end)
    box_geometry: str = ""               # '550x320+100+100'
    box_open: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "mode": self.mode,
            "region_single": self.region_single, "region_a": self.region_a, "region_b": self.region_b,
            "ocr_engine": self.ocr_engine, "alphabet": self.alphabet, "target": self.target,
            "interval": self.interval, "preprocess": self.preprocess.to_dict(),
            "font_size": self.font_size, "font_family": self.font_family, "box_geometry": self.box_geometry, "box_open": self.box_open,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "Profile":
        d = d or {}
        p = cls()
        p.name = str(d.get("name") or p.name)[:60]
        p.mode = "dual" if d.get("mode") == "dual" else "single"
        p.region_single = _bbox(d.get("region_single"))
        p.region_a = _bbox(d.get("region_a"))
        p.region_b = _bbox(d.get("region_b"))
        p.ocr_engine = str(d.get("ocr_engine") or p.ocr_engine)
        alpha = d.get("alphabet", p.alphabet)
        p.alphabet = alpha if alpha in ALPHABETS else DEFAULT_ALPHABET
        tgt = d.get("target", p.target)
        p.target = NAME_TO_CODE.get(tgt, tgt) if tgt not in LANG_NAMES else tgt   # aceita nomes do v2
        if p.target not in LANG_NAMES:
            p.target = "pt"
        try:
            p.interval = max(0.2, min(5.0, float(d.get("interval", p.interval))))
            p.font_size = max(8, min(72, int(d.get("font_size", p.font_size))))
        except (TypeError, ValueError):
            pass
        ff = str(d.get("font_family") or "default")
        p.font_family = ff if re.fullmatch(r"[a-z0-9_-]{1,32}", ff) else "default"      # só um id simples (nunca CSS)
        p.preprocess = PreprocessOptions.from_dict(d.get("preprocess"))
        p.box_geometry = str(d.get("box_geometry") or "")
        p.box_open = bool(d.get("box_open", False))
        return p

    def channels(self) -> dict[str, tuple]:
        """Canais ativos → bbox. 'uni' (modo único) ou 'a'/'b' (modo dual)."""
        out: dict[str, tuple] = {}
        if self.mode == "dual":
            if self.region_a:
                out["a"] = tuple(self.region_a)
            if self.region_b:
                out["b"] = tuple(self.region_b)
        elif self.region_single:
            out["uni"] = tuple(self.region_single)
        return out


def slug(name: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip().replace(" ", "_")
    return s[:60] or "perfil"


class ProfileStore:
    def __init__(self, directory: Optional[Path] = None):
        self.dir = Path(directory) if directory else paths.profiles_dir()
        self.dir.mkdir(parents=True, exist_ok=True)

    def _file(self, name: str) -> Path:
        return self.dir / f"{slug(name)}.json"

    def list(self) -> list[str]:
        names = []
        for f in sorted(self.dir.glob("*.json")):
            if f.stem == LAST_SESSION:
                continue
            try:
                names.append(str(json.loads(f.read_text(encoding="utf-8")).get("name") or f.stem))
            except (OSError, ValueError):
                continue
        return names

    def save(self, profile: Profile) -> Path:
        f = self._file(profile.name)
        f.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return f

    def load(self, name: str) -> Optional[Profile]:
        try:
            return Profile.from_dict(json.loads(self._file(name).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log.warning("perfil %r ilegível: %s", name, exc)
            return None

    def delete(self, name: str) -> bool:
        try:
            self._file(name).unlink()
            return True
        except OSError:
            return False

    # sessão automática
    def save_last(self, profile: Profile) -> None:
        d = profile.to_dict()
        (self.dir / f"{LAST_SESSION}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_last(self) -> Optional[Profile]:
        try:
            return Profile.from_dict(json.loads((self.dir / f"{LAST_SESSION}.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None
