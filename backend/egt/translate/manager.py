"""Gerenciador de tradução: cache → motores online/offline em cadeia, com backoff.

Translation manager: cache first, then engine fallback chain with rate-limit/backoff.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable, Optional

from ..change import normalize_text
from .base import RateLimited, TranslationError, TranslationResult, Translator
from .cache import TranslationCache

log = logging.getLogger(__name__)

MAX_COOLDOWN = 120.0
_WORD = re.compile(r"[^\W\d_]{2,}")


def is_echo(text: str, out: str, src: str = "", tgt: str = "") -> bool:
    """O motor devolveu o próprio texto sem traduzir? (ex.: instâncias do Lingva em 2026).
    Só conta para frases reais (2+ palavras); nomes/siglas iguais na tradução são normais."""
    if src and tgt and src == tgt:
        return False
    a, b = normalize_text(text).casefold(), normalize_text(out).casefold()
    if a != b:
        return False
    return len(_WORD.findall(a)) >= 2 or (len(a) >= 4 and not a.isascii() and sum(c.isalpha() for c in a) >= 4)


def error_code(exc: Exception) -> str:
    return str(getattr(exc, "code", "") or ("rate_limit" if isinstance(exc, RateLimited) else "http"))


class _EngineState:
    __slots__ = ("fails", "until", "last_error", "last_code", "last_ok")

    def __init__(self):
        self.fails = 0
        self.until = 0.0
        self.last_error = ""
        self.last_code = ""
        self.last_ok = 0.0      # time.time() do último sucesso


class TranslationManager:
    """
    `engines_provider()` devolve a lista ORDENADA de Translators ativos (IA primeiro,
    se ligada). Para cada motor: consulta o cache (texto, src, tgt, motor); se não houver,
    traduz ao vivo. Se falhar, entra em espera exponencial e passa para o próximo.
    No modo "somente cache" nunca chama a rede.
    """

    def __init__(self, cache: TranslationCache, engines_provider: Callable[[], list[Translator]],
                 cache_only_provider: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic):
        self.cache = cache
        self._engines = engines_provider
        self._cache_only = cache_only_provider
        self._clock = clock
        self._state: dict[str, _EngineState] = {}
        self._lock = threading.Lock()
        self.stats = {"requests": 0, "cache_hits": 0, "live": 0, "errors": 0, "passthrough": 0}
        self.last_latency_ms = 0.0

    # -- estado / backoff
    def _st(self, eid: str) -> _EngineState:
        with self._lock:
            return self._state.setdefault(eid, _EngineState())

    def _fail(self, eid: str, exc: Exception) -> None:
        st = self._st(eid)
        st.fails += 1
        delay = min(MAX_COOLDOWN, 2.0 ** min(st.fails, 7))
        if isinstance(exc, RateLimited) and exc.retry_after:
            delay = max(delay, min(float(exc.retry_after), 3600.0))
        if getattr(exc, "code", "") in ("no_key", "bad_key", "config", "unsupported_lang"):
            delay = max(delay, 30.0)               # configuração errada: não adianta insistir logo
        st.until = self._clock() + delay
        st.last_error = str(exc)
        st.last_code = error_code(exc)
        log.warning("motor %s falhou (%s); em espera por %.0fs", eid, exc, delay)

    def _ok(self, eid: str) -> None:
        st = self._st(eid)
        st.fails, st.until, st.last_error, st.last_code, st.last_ok = 0, 0.0, "", "", time.time()

    def engine_status(self) -> dict[str, dict]:
        now = self._clock()
        with self._lock:
            return {k: {"fails": v.fails, "cooldown": max(0.0, v.until - now), "error": v.last_error,
                        "code": v.last_code, "last_ok": v.last_ok}
                    for k, v in self._state.items()}

    def clear_backoff(self, eid: str) -> None:
        with self._lock:
            self._state.pop(eid, None)

    def test_engine(self, eng: Translator, text: str, src: str, tgt: str) -> dict:
        """Testa UM motor ao vivo (sem cache, ignorando a espera). Atualiza o estado dele. Nunca levanta."""
        t0 = time.perf_counter()
        text = (text or "").strip()
        out = {"engine": eng.id, "ok": False, "text": "", "code": "", "message": "", "ms": 0}
        ok, why = eng.available()
        if not ok:
            out.update(code=eng.unavailable_code(why), message=why)
            return out
        try:
            res = (eng.translate(text, src, tgt) or "").strip()
            if not res:
                raise TranslationError("resposta vazia", "empty")
            if is_echo(text, res, src, tgt):
                raise TranslationError("devolveu o texto sem traduzir", "echo")
        except Exception as exc:  # noqa: BLE001
            if not isinstance(exc, TranslationError):
                log.exception("erro inesperado no teste do motor %s", eng.id)
            self._fail(eng.id, exc)
            out.update(code=error_code(exc) if isinstance(exc, TranslationError) else "http",
                       message=str(exc) if isinstance(exc, TranslationError) else type(exc).__name__)
        else:
            self._ok(eng.id)
            out.update(ok=True, text=res)
        out["ms"] = round((time.perf_counter() - t0) * 1000)
        return out

    def reset_backoff(self) -> None:
        with self._lock:
            self._state.clear()

    @property
    def hit_rate(self) -> float:
        n = self.stats["requests"] - self.stats["passthrough"]
        return (self.stats["cache_hits"] / n) if n > 0 else 0.0

    # -- tradução
    def translate(self, text: str, src: str, tgt: str) -> TranslationResult:
        t0 = time.perf_counter()
        text = (text or "").strip()
        self.stats["requests"] += 1
        res = TranslationResult("", src=src, tgt=tgt)
        if not text:
            res.ok, res.error = False, "texto vazio"
            return res
        if src and src == tgt:
            self.stats["passthrough"] += 1
            res.text, res.engine = text, "none"
            return res

        engines = self._engines()
        cache_only = self._cache_only()
        key_src = src or "auto"
        echo: Optional[tuple[str, str]] = None      # (motor, texto) — usado só se nenhum traduzir de verdade

        for eng in engines:
            hit = self.cache.get(text, key_src, tgt, eng.id)
            if hit is not None:
                self.stats["cache_hits"] += 1
                res.text, res.engine, res.cached = hit, eng.id, True
                res.attempts.append((eng.id, "cache"))
                break
            if cache_only:
                continue
            if self._st(eng.id).until > self._clock():
                res.attempts.append((eng.id, "em espera"))
                continue
            ok, why = eng.available()
            if not ok:
                res.attempts.append((eng.id, f"indisponível: {why}"))
                continue
            try:
                out = (eng.translate(text, src, tgt) or "").strip()
                if not out:
                    raise TranslationError("resposta vazia", "empty")
            except (TranslationError, RateLimited) as exc:
                self._fail(eng.id, exc)
                res.attempts.append((eng.id, str(exc)))
                res.codes[eng.id] = error_code(exc)
                continue
            except Exception as exc:  # bug/rede inesperados: nunca derruba o pipeline
                log.exception("erro inesperado no motor %s", eng.id)
                self._fail(eng.id, exc)
                res.attempts.append((eng.id, f"{type(exc).__name__}: {exc}"))
                res.codes[eng.id] = "http"
                continue
            if is_echo(text, out, src, tgt):           # nunca vai para o cache; tenta o próximo motor
                res.attempts.append((eng.id, "devolveu o texto sem traduzir"))
                res.codes[eng.id] = "echo"
                if echo is None:
                    echo = (eng.id, out)
                continue
            self._ok(eng.id)
            self.stats["live"] += 1
            self.cache.put(text, key_src, tgt, eng.id, out)
            res.text, res.engine = out, eng.id
            res.attempts.append((eng.id, "ok"))
            break
        else:
            if echo is not None:                    # todos ecoaram: provavelmente já estava no idioma certo
                res.text, res.engine = echo[1], echo[0]
            else:
                self.stats["errors"] += 1
                res.ok = False
                if cache_only:
                    res.error = "modo somente cache: tradução não encontrada"
                elif not engines:
                    res.error = "nenhum motor de tradução ativo"
                else:
                    res.error = "; ".join(f"{e}: {m}" for e, m in res.attempts) or "falha"
        res.elapsed_ms = (time.perf_counter() - t0) * 1000
        self.last_latency_ms = res.elapsed_ms
        return res


def engine_factories(settings) -> dict:
    """{id: fábrica} de todos os motores comuns (sem I/O de rede). Catálogo em providers.py."""
    from .providers import factories
    return factories(settings)


AI_MODES = ("off", "gemini", "ollama")


def ai_engine(settings, mode: str):
    """O motor de IA de `mode` ('gemini' | 'ollama'), ou None. Nunca cria o outro."""
    from .ai import GeminiTranslate, OllamaTranslate
    ai = settings.section("ai")
    ctx = lambda: settings.get("ai.context", "")  # noqa: E731
    if mode == "ollama":
        return OllamaTranslate(ai.get("ollama_url", ""), ai.get("ollama_model", ""), ctx)
    if mode == "gemini":
        return GeminiTranslate(settings.gemini_key, ai.get("gemini_model") or "gemini-3.5-flash-lite", ctx)
    return None


def build_engines(settings, ai_mode: Optional[str] = None) -> list[Translator]:
    """Monta a lista ordenada de motores a partir das configurações (sem I/O de rede).
    Só a IA selecionada em ai.mode entra (na frente); 'off' = nenhuma IA."""
    factories = engine_factories(settings)
    tr = settings.section("translation")
    enabled = set(tr.get("enabled", []))
    order = [e for e in tr.get("order", []) if e in factories]
    order += [e for e in factories if e not in order]
    out: list[Translator] = [factories[e]() for e in order if e in enabled]
    mode = settings.get("ai.mode", "off") if ai_mode is None else ai_mode
    eng = ai_engine(settings, mode) if mode in AI_MODES else None
    if eng is not None:
        out.insert(0, eng)
    return out


def normalized(text: str) -> str:
    return normalize_text(text)
