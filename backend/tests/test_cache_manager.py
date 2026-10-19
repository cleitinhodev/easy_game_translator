import pytest

from egt.db import Database
from egt.history import HistoryStore
from egt.translate import TranslationCache, TranslationManager
from egt.translate.base import RateLimited, TranslationError, Translator


class Fake(Translator):
    def __init__(self, id_, fn=None, available=True):
        self.id = id_
        self.name = id_
        self.calls = 0
        self.fn = fn or (lambda t, s, g: f"[{self.id}] {t}")
        self._available = available

    def available(self):
        return (self._available, "" if self._available else "off")

    def translate(self, text, src, tgt):
        self.calls += 1
        return self.fn(text, src, tgt)


@pytest.fixture
def cache():
    return TranslationCache(Database())


def mk(cache, engines, cache_only=False, clock=None):
    now = [0.0]
    mgr = TranslationManager(cache, lambda: engines, lambda: cache_only,
                             clock=clock or (lambda: now[0]))
    mgr._now = now
    return mgr


def test_cache_roundtrip_and_normalization(cache):
    cache.put("Hello   world", "en", "pt", "google", "Olá mundo")
    assert cache.get(" Hello world ", "en", "pt", "google") == "Olá mundo"
    assert cache.get("Hello world", "en", "pt", "mymemory") is None
    assert cache.get("Hello world", "en", "es", "google") is None
    assert cache.stats()["entries"] == 1
    cache.clear()
    assert cache.count() == 0


def test_cache_prune(cache):
    cache.max_rows = 5
    for i in range(10):
        cache.put(f"text {i}", "en", "pt", "g", f"t{i}")
    cache.prune()
    assert cache.count() == 5


def test_second_call_hits_cache(cache):
    f = Fake("google")
    m = mk(cache, [f])
    r1 = m.translate("Hello", "en", "pt")
    r2 = m.translate("Hello", "en", "pt")
    assert r1.ok and not r1.cached and r2.cached and f.calls == 1
    assert r2.engine == "google" and m.hit_rate == 0.5


def test_fallback_chain_and_backoff(cache):
    def boom(t, s, g):
        raise TranslationError("down")

    a, b = Fake("a", boom), Fake("b")
    m = mk(cache, [a, b])
    r = m.translate("Hi there", "en", "pt")
    assert r.ok and r.engine == "b" and a.calls == 1
    # 'a' está em espera: não é chamado de novo
    m.translate("Another one", "en", "pt")
    assert a.calls == 1
    # depois do cooldown, volta a tentar
    m._now[0] += 10
    m.translate("Third text", "en", "pt")
    assert a.calls == 2


def test_rate_limit_retry_after(cache):
    def rl(t, s, g):
        raise RateLimited("429", retry_after=100)

    a = Fake("a", rl)
    m = mk(cache, [a, Fake("b")])
    m.translate("x y z", "en", "pt")
    m._now[0] += 50
    m.translate("x y z 2", "en", "pt")
    assert a.calls == 1
    m._now[0] += 60
    m.translate("x y z 3", "en", "pt")
    assert a.calls == 2


def test_all_fail(cache):
    def boom(t, s, g):
        raise TranslationError("down")

    m = mk(cache, [Fake("a", boom), Fake("b", boom)])
    r = m.translate("Hello", "en", "pt")
    assert not r.ok and "a:" in r.error


def test_unavailable_skipped(cache):
    m = mk(cache, [Fake("a", available=False), Fake("b")])
    r = m.translate("Hello", "en", "pt")
    assert r.engine == "b"


def test_cache_only_mode(cache):
    f = Fake("google")
    cache.put("Known", "en", "pt", "google", "Conhecido")
    m = mk(cache, [f], cache_only=True)
    assert m.translate("Known", "en", "pt").text == "Conhecido"
    r = m.translate("Unknown", "en", "pt")
    assert not r.ok and f.calls == 0


def test_same_language_passthrough(cache):
    f = Fake("google")
    r = mk(cache, [f]).translate("Olá", "pt", "pt")
    assert r.ok and r.text == "Olá" and f.calls == 0


def test_unexpected_exception_is_contained(cache):
    def bug(t, s, g):
        raise ValueError("bug")

    m = mk(cache, [Fake("a", bug), Fake("b")])
    assert m.translate("Hello", "en", "pt").engine == "b"


def test_engine_order_and_cache_per_engine(cache):
    a, b = Fake("a"), Fake("b")
    cache.put("Hi", "en", "pt", "b", "from-b")
    m = mk(cache, [a, b])
    # 'a' vem primeiro: consulta cache de 'a' (vazio) e traduz ao vivo
    assert m.translate("Hi", "en", "pt").engine == "a"


def test_history_export(tmp_path):
    db = Database()
    h = HistoryStore(db)
    h.add("Hello", "Olá", engine="google", src="en", tgt="pt")
    h.add("Bye", "Tchau", from_cache=True)
    assert h.count() == 2 and h.recent(1)[0]["original"] == "Bye"
    for ext in ("txt", "csv", "json"):
        p = tmp_path / f"h.{ext}"
        assert h.export(p) == 2
        assert "Hello" in p.read_text(encoding="utf-8-sig")
    h.clear()
    assert h.count() == 0
