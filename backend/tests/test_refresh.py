"""Mudanças de configuração com o pipeline rodando devem reprocessar na hora (imagem estática)."""
import time

from egt.ocr.base import OcrResult
from egt.pipeline import Pipeline, PipelineConfig
from egt.preprocess import PreprocessOptions
from egt.translate.base import TranslationResult
from egt.translate.cache import TranslationCache
from egt.db import Database

from tests.test_pipeline import Cap, FakeOcr, kinds, wait_for


class EngineOcr(FakeOcr):
    """OCR cujo texto depende do 'motor' (para provar que o OCR foi refeito)."""

    def __init__(self, tag):
        super().__init__([f"Hello from {tag}"])
        self.tag = tag


def build(ocr_by_engine=None, **cfg):
    cap = Cap()
    ocr_by_engine = ocr_by_engine or {"fake": FakeOcr(["Hello world"])}
    calls = []

    def tr(text, src, tgt):
        calls.append((text, tgt))
        return TranslationResult(f"{tgt.upper()}:{text}", engine="fake", src=src, tgt=tgt)

    base = dict(channels={"uni": (0, 0, 200, 60)}, interval=0.15, stable_ms=0, ocr_engine="fake",
                preprocess=PreprocessOptions(scale=1))
    base.update(cfg)
    p = Pipeline(cap, lambda eid: ocr_by_engine[eid], tr, config=PipelineConfig(**base))
    return p, cap, calls, ocr_by_engine


def translations(evs):
    return [e for e in evs if e.kind == "translation"]


def test_target_change_retranslates_static_image_without_new_ocr():
    p, cap, calls, ocrs = build()
    p.start()
    try:
        seen = wait_for(p, lambda ev: len(translations(ev)) >= 1)
        assert translations(seen)[0].data["translated"] == "PT:Hello world"
        time.sleep(0.6)                         # imagem parada: nada novo deve chegar
        assert not translations(p.drain())
        ocr_calls = ocrs["fake"].calls
        cap_calls = cap.calls

        from dataclasses import replace
        p.set_config(replace(p.config, target="en"))   # só muda o idioma de destino

        seen = wait_for(p, lambda ev: len(translations(ev)) >= 1)
        tr = translations(seen)
        assert tr and tr[0].data["translated"] == "EN:Hello world" and tr[0].data["tgt"] == "en"
        assert "pending" in kinds(seen)                 # a UI recebe o estado "traduzindo…"
        assert calls[-1] == ("Hello world", "en")
        assert ocrs["fake"].calls == ocr_calls          # reutilizou o texto: sem novo OCR
        assert cap.calls >= cap_calls
    finally:
        p.stop(wait=True)


def test_ocr_engine_change_recaptures_and_reocrs_static_image():
    ocrs = {"a": FakeOcr(["Text from A"]), "b": FakeOcr(["Text from B"])}
    p, cap, calls, _ = build(ocrs, ocr_engine="a")
    p.start()
    try:
        seen = wait_for(p, lambda ev: len(translations(ev)) >= 1)
        assert translations(seen)[0].data["original"] == "Text from A"
        time.sleep(0.5)
        assert not translations(p.drain())
        from dataclasses import replace
        p.set_config(replace(p.config, ocr_engine="b"))
        seen = wait_for(p, lambda ev: any(e.kind == "translation" and e.data["original"] == "Text from B" for e in ev))
        assert any(e.kind == "translation" and e.data["original"] == "Text from B" for e in seen)
        assert ocrs["b"].calls >= 1
        assert "pending" in kinds(seen)
    finally:
        p.stop(wait=True)


def test_alphabet_and_preprocess_change_force_full_refresh():
    for field, value in (("alphabet", "abc(ES)"), ("preprocess", PreprocessOptions(scale=2, grayscale=False))):
        p, cap, calls, ocrs = build()
        p.start()
        try:
            wait_for(p, lambda ev: len(translations(ev)) >= 1)
            time.sleep(0.4)
            p.drain()
            before = ocrs["fake"].calls
            from dataclasses import replace
            p.set_config(replace(p.config, **{field: value}))
            seen = wait_for(p, lambda ev: len(translations(ev)) >= 1)
            assert translations(seen), field
            assert ocrs["fake"].calls > before, field       # OCR refeito
        finally:
            p.stop(wait=True)


def test_explicit_refresh_modes_and_noop_when_stopped():
    p, cap, calls, ocrs = build()
    assert p.refresh("full") is False                      # parado: nada a fazer
    p.start()
    try:
        wait_for(p, lambda ev: len(translations(ev)) >= 1)
        time.sleep(0.4)
        p.drain()
        n = len(calls)
        assert p.refresh("translate") is True
        seen = wait_for(p, lambda ev: len(translations(ev)) >= 1)
        assert translations(seen) and len(calls) == n + 1
        assert p.refresh("full") is True
        seen = wait_for(p, lambda ev: len(translations(ev)) >= 1)
        assert translations(seen)
    finally:
        p.stop(wait=True)


def test_unrelated_config_change_does_not_reprocess():
    p, cap, calls, ocrs = build()
    p.start()
    try:
        wait_for(p, lambda ev: len(translations(ev)) >= 1)
        time.sleep(0.4)
        p.drain()
        n = len(calls)
        p.update_config(interval=0.3)
        from dataclasses import replace
        p.set_config(replace(p.config, interval=0.2, stable_ms=100))
        time.sleep(0.8)
        assert len(calls) == n and not translations(p.drain())
    finally:
        p.stop(wait=True)


def test_stale_translation_is_discarded_after_target_change():
    """Uma tradução lenta com o idioma antigo não pode aparecer depois da mudança."""
    import threading
    gate = threading.Event()
    calls = []

    def slow_tr(text, src, tgt):
        calls.append(tgt)
        if tgt == "pt":
            gate.wait(3)
        return TranslationResult(f"{tgt}:{text}", engine="fake", src=src, tgt=tgt)

    cap = Cap(); ocr = FakeOcr(["Hello world"])
    p = Pipeline(cap, lambda e: ocr, slow_tr, config=PipelineConfig(
        channels={"uni": (0, 0, 200, 60)}, interval=0.15, stable_ms=0, preprocess=PreprocessOptions(scale=1), target="pt"))
    p.start()
    try:
        time.sleep(0.5)                                    # job "pt" travado dentro do tradutor
        from dataclasses import replace
        p.set_config(replace(p.config, target="en"))
        time.sleep(0.3)
        gate.set()
        seen = wait_for(p, lambda ev: any(e.kind == "translation" for e in ev))
        time.sleep(0.5)
        seen += p.drain()
        tgts = [e.data["tgt"] for e in translations(seen)]
        assert "en" in tgts and "pt" not in tgts
    finally:
        gate.set()
        p.stop(wait=True)


def test_cache_key_includes_target_language(tmp_path):
    cache = TranslationCache(Database(tmp_path / "c.sqlite"))
    cache.put("Hello", "en", "pt", "google", "Olá")
    assert cache.get("Hello", "en", "pt", "google") == "Olá"
    assert cache.get("Hello", "en", "es", "google") is None     # outro destino não reaproveita
    cache.put("Hello", "en", "es", "google", "Hola")
    assert cache.get("Hello", "en", "pt", "google") == "Olá"
    assert cache.get("Hello", "en", "es", "google") == "Hola"
