"""Idiomas de destino, alfabetos de OCR e detecção de idioma de origem.

Target languages, OCR alphabets and source-language detection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# (código interno, nome exibido como no original)
TARGET_LANGUAGES: list[tuple[str, str]] = [
    ("pt", "Português"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("bn", "বাংলা"),
    ("ja", "日本語"),
    ("zh-CN", "中文 (Simplificado)"),
    ("zh-TW", "中文 (Tradicional)"),
    ("zh-HK", "中文 (Hong Kong)"),
    ("ko", "한국어"),
    ("hi", "हिन्दी"),
    ("ru", "Русский"),
    ("id", "Bahasa Indonesia"),
    ("tr", "Türkçe"),
    ("ar", "العربية"),
    ("ur", "اردو"),
]
LANG_NAMES = dict(TARGET_LANGUAGES)
# compatibilidade com o v2 (nome → código)
NAME_TO_CODE = {name: code for code, name in TARGET_LANGUAGES}


def lang_label(code: str) -> str:
    """Rótulo para dropdown: '[PT] Português'."""
    short = code.upper() if code.startswith("zh") else code.split("-")[0].upper()
    return f"[{short}] {LANG_NAMES.get(code, code)}"


def label_to_code(label: str) -> str:
    for code, _ in TARGET_LANGUAGES:
        if lang_label(code) == label:
            return code
    if label in NAME_TO_CODE:
        return NAME_TO_CODE[label]
    return label if label in LANG_NAMES else "pt"


def normalize_lang(code: str) -> str:
    """Normaliza códigos vindos do langdetect/outros: 'zh-cn' → 'zh-CN'."""
    if not code:
        return ""
    c = code.strip().replace("_", "-")
    low = c.lower()
    special = {"zh-cn": "zh-CN", "zh-tw": "zh-TW", "zh-hk": "zh-HK", "zh": "zh-CN",
               "pt-br": "pt", "pt-pt": "pt", "iw": "he", "jw": "jv"}
    if low in special:
        return special[low]
    return low.split("-")[0] if "-" in low else low


def engine_lang(engine: str, code: str) -> str:
    """Converte nosso código para o dialeto do motor de tradução."""
    code = normalize_lang(code)
    if not code:
        return "auto"
    if code == "zh-HK":  # nenhum motor gratuito distingue HK
        code = "zh-TW"
    if engine == "argos":
        return "zh" if code.startswith("zh") else code
    if engine in ("libre", "lingva"):
        if code.startswith("zh"):
            return "zh-Hant" if (code == "zh-TW" and engine == "libre") else "zh"
        return code
    if engine == "mymemory":
        return {"pt": "pt-BR", "en": "en-GB"}.get(code, code)
    return code  # google / microsoft / IA


# ----------------------------------------------------------------- Alfabetos


@dataclass(frozen=True)
class Alphabet:
    key: str                      # símbolo exibido (compatível com o v2)
    tesseract: str
    rapid: Optional[str]          # None = não suportado pelo RapidOCR padrão
    easy: tuple
    paddle: Optional[str]
    winocr: str
    hint: str                     # idioma de origem provável
    cjk: bool = False
    latin: bool = False
    title: str = ""


ALPHABETS: dict[str, Alphabet] = {a.key: a for a in [
    Alphabet("abc(EN)", "eng", "en", ("en",), "en", "en-US", "en", latin=True, title="Latin · English"),
    Alphabet("abc(BR)", "por", "en", ("pt", "en"), "latin", "pt-BR", "pt", latin=True, title="Latin · Português"),
    Alphabet("你", "chi_sim", "ch", ("ch_sim", "en"), "ch", "zh-Hans-CN", "zh-CN", cjk=True, title="中文"),
    Alphabet("अ", "hin", None, ("hi", "en"), "hi", "hi", "hi", title="हिन्दी"),
    Alphabet("ب", "ara", None, ("ar", "en"), "ar", "ar", "ar", title="العربية"),
    Alphabet("অ", "ben", None, ("bn", "en"), None, "bn-IN", "bn", title="বাংলা"),
    Alphabet("абв", "rus", None, ("ru", "en"), "cyrillic", "ru", "ru", title="Русский"),
    Alphabet("あ", "jpn", None, ("ja", "en"), "japan", "ja", "ja", cjk=True, title="日本語"),
    Alphabet("가", "kor", None, ("ko", "en"), "korean", "ko", "ko", cjk=True, title="한국어"),
]}
DEFAULT_ALPHABET = "abc(EN)"


def alphabet(key: str) -> Alphabet:
    return ALPHABETS.get(key) or ALPHABETS[DEFAULT_ALPHABET]


_CJK = "\u3000-\u9fff\uac00-\ud7af\uff00-\uffef"
_CJK_GAP = re.compile(rf"(?<=[{_CJK}])[ \t]+(?=[{_CJK}])")


def clean_ocr_text(text: str, alpha_key: str) -> str:
    """Pós-processa o texto do OCR (espaços, ajustes por alfabeto)."""
    if not text:
        return ""
    a = alphabet(alpha_key)
    text = text.replace("\r", "")
    if a.cjk:
        text = _CJK_GAP.sub("", text)  # Tesseract coloca espaço entre ideogramas
    if alpha_key == "abc(EN)":
        text = re.sub(r"(?<![\w|])\|(?![\w|])", "I", text)  # '|' isolado vira 'I' (como no v2)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


# ------------------------------------------------------------ Detecção de idioma

_detector_ready = False


def _langdetect():
    global _detector_ready
    import langdetect
    if not _detector_ready:
        langdetect.DetectorFactory.seed = 0  # resultados determinísticos
        _detector_ready = True
    return langdetect


def detect_source(text: str, alpha_key: str = DEFAULT_ALPHABET) -> str:
    """Idioma de origem provável. Alfabetos não latinos usam o palpite do alfabeto;
    os latinos passam pelo langdetect (com fallback no alfabeto)."""
    a = alphabet(alpha_key)
    if not a.latin:
        if alpha_key == "ب":
            guess = _safe_detect(text)
            return guess if guess in ("ur", "fa", "ar") else a.hint
        return a.hint
    if len(re.sub(r"\W", "", text)) < 12:
        return a.hint  # texto curto: langdetect é pouco confiável
    return _safe_detect(text) or a.hint


def _safe_detect(text: str) -> str:
    try:
        return normalize_lang(_langdetect().detect(text))
    except Exception:
        return ""


def detect_any(text: str) -> str:
    """Detecta o idioma de qualquer texto (tradução manual). '' se incerto."""
    if len(text.strip()) < 3:
        return ""
    return _safe_detect(text)


_SENT_END = ".!?:;。！？…"


def smart_join_lines(text: str, cjk: bool = False) -> str:
    """Junta linhas quebradas pelo layout do jogo (legenda em 2 linhas) para traduzir a frase inteira.

    Mantém a quebra quando a linha anterior termina em pontuação final (ex.: duas falas de chat).
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) <= 1:
        return lines[0] if lines else ""
    out = lines[0]
    for ln in lines[1:]:
        if out[-1] in _SENT_END:
            out += "\n" + ln
        else:
            out += ("" if cjk else " ") + ln
    return out
