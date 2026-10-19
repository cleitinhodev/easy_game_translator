"""Gerenciador de tradução: cache → motores online/offline em cadeia, com backoff.

Translation manager: cache first, then engine fallback chain with rate-limit/backoff.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from ..change import normalize_text
from .base import RateLimited, TranslationError, TranslationResult, Translator
from .cache import TranslationCache

log = logging.getLogger(__name__)

MAX_COOLDOWN = 120.0


class _EngineState:
    __slots__ = ("fails", "until", "last_error")

    def __init__(self):
        self.fails = 0
        self.until = 0.0
        self.last_error = ""


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
        st.until = self._clock() + delay
        st.last_error = str(exc)
        log.warning("motor %s falhou (%s); em espera por %.0fs", eid, exc, delay)

    def _ok(self, eid: str) -> None:
        st = self._st(eid)
        st.fails, st.until, st.last_error = 0, 0.0, ""

    def engine_status(self) -> dict[str, dict]:
        now = self._clock()
        with self._lock:
            return {k: {"fails": v.fails, "cooldown": max(0.0, v.until - now), "error": v.last_error}
                    for k, v in self._state.items()}

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
                    raise TranslationError("resposta vazia")
            except (TranslationError, RateLimited) as exc:
                self._fail(eng.id, exc)
                res.attempts.append((eng.id, str(exc)))
                continue
            except Exception as exc:  # bug/rede inesperados: nunca derruba o pipeline
                log.exception("erro inesperado no motor %s", eng.id)
                self._fail(eng.id, exc)
                res.attempts.append((eng.id, f"{type(exc).__name__}: {exc}"))
                continue
            self._ok(eng.id)
            self.stats["live"] += 1
            self.cache.put(text, key_src, tgt, eng.id, out)
            res.text, res.engine = out, eng.id
            res.attempts.append((eng.id, "ok"))
            break
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
    """{id: fábrica} de todos os motores comuns (sem I/O de rede)."""
    from .ai import GeminiTranslate, OllamaTranslate
    from .argos import ArgosTranslate
    from .google import GoogleTranslate
    from .libre import LibreTranslate, LingvaTranslate
    from .microsoft import MicrosoftTranslate
    from .mymemory import MyMemoryTranslate

    tr = settings.section("translation")
    timeout = float(tr.get("timeout", 8.0))
    factories = {
        "google": lambda: GoogleTranslate(),
        "mymemory": lambda: MyMemoryTranslate(timeout=timeout),
        "libre": lambda: LibreTranslate(tr.get("libre_url", ""), tr.get("libre_key", ""), timeout),
        "lingva": lambda: LingvaTranslate(tr.get("lingva_url", ""), timeout),
        "microsoft": lambda: MicrosoftTranslate(tr.get("microsoft_key", ""), tr.get("microsoft_region", "")),
        "argos": lambda: ArgosTranslate(),
    }
    return factories


def build_engines(settings, ai_enabled: Optional[bool] = None) -> list[Translator]:
    """Monta a lista ordenada de motores a partir das configurações (sem I/O de rede)."""
    from .ai import GeminiTranslate, OllamaTranslate
    factories = engine_factories(settings)
    tr = settings.section("translation")
    enabled = set(tr.get("enabled", []))
    order = [e for e in tr.get("order", []) if e in factories]
    order += [e for e in factories if e not in order]
    out: list[Translator] = [factories[e]() for e in order if e in enabled]

    ai = settings.section("ai")
    use_ai = ai.get("enabled", False) if ai_enabled is None else ai_enabled
    if use_ai:
        ctx = lambda: settings.get("ai.context", "")  # noqa: E731
        if ai.get("provider") == "ollama":
            out.insert(0, OllamaTranslate(ai.get("ollama_url", ""), ai.get("ollama_model", ""), ctx))
        else:
            out.insert(0, GeminiTranslate(settings.gemini_key, ai.get("gemini_model", "gemini-2.5-flash"), ctx))
    return out


def normalized(text: str) -> str:
    return normalize_text(text)
