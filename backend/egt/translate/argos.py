"""Argos Translate — tradução OFFLINE (opcional: pip install argostranslate)."""
from __future__ import annotations

import logging

from ..languages import engine_lang
from .base import TranslationError, Translator

log = logging.getLogger(__name__)


def module_present() -> bool:
    from ..ocr.base import module_available
    return module_available("argostranslate")


def installed_pairs() -> list[tuple[str, str]]:
    """Pares (origem, destino) instalados."""
    if not module_present():
        return []
    try:
        import argostranslate.translate as at
        langs = at.get_installed_languages()
        pairs = []
        for a in langs:
            for b in langs:
                if a.code != b.code and a.get_translation(b) is not None:
                    pairs.append((a.code, b.code))
        return pairs
    except Exception as exc:
        log.debug("argos: %s", exc)
        return []


def install_pair(src: str, tgt: str) -> str:
    """Baixa e instala o pacote src→tgt (precisa de internet uma vez)."""
    import argostranslate.package as ap
    s, t = engine_lang("argos", src), engine_lang("argos", tgt)
    ap.update_package_index()
    for pkg in ap.get_available_packages():
        if pkg.from_code == s and pkg.to_code == t:
            ap.install_from_path(pkg.download())
            return f"{s}→{t} instalado"
    raise TranslationError(f"Argos: nenhum pacote {s}→{t} no índice")


class ArgosTranslate(Translator):
    id = "argos"
    name = "Argos (offline)"
    online = False
    optional_dep = "pip install argostranslate"

    def available(self) -> tuple[bool, str]:
        if not module_present():
            return False, self.optional_dep
        if not installed_pairs():
            return False, "nenhum pacote de idioma instalado"
        return True, "ok"

    def translate(self, text: str, src: str, tgt: str) -> str:
        try:
            import argostranslate.translate as at
        except ImportError as exc:
            raise TranslationError("argostranslate não instalado") from exc
        s, t = (engine_lang("argos", src) if src else ""), engine_lang("argos", tgt)
        try:
            if not s or s == "auto":
                raise TranslationError("Argos precisa do idioma de origem")
            langs = {lg.code: lg for lg in at.get_installed_languages()}
            if s not in langs or t not in langs:
                raise TranslationError(f"Argos: pacote {s}→{t} não instalado")
            tr = langs[s].get_translation(langs[t])
            if tr is None:
                # tenta ponte via inglês
                if s != "en" and t != "en" and "en" in langs:
                    mid = langs[s].get_translation(langs["en"])
                    end = langs["en"].get_translation(langs[t])
                    if mid and end:
                        return end.translate(mid.translate(text))
                raise TranslationError(f"Argos: pacote {s}→{t} não instalado")
            return tr.translate(text)
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(f"Argos: {type(exc).__name__}: {exc}") from exc
