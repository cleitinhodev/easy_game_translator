"""Controlador central (sem interface): serviços, perfil atual, pipeline e eventos.

Headless controller: services + current profile + pipeline. A camada HTTP/WebSocket
(`egt.server`) e os testes só falam com esta classe.
"""
from __future__ import annotations

import logging
import re
import socket
import time
from typing import Callable, Optional

from . import ocr as ocr_mod
from . import paths
from .capture.screen import ScreenGrabber, list_monitors, normalize_bbox
from .config import Settings
from .db import Database
from .glossary import Glossary
from .history import HistoryStore
from .languages import ALPHABETS, TARGET_LANGUAGES, detect_any
from .pipeline import Event, Pipeline, PipelineConfig
from .preprocess import PreprocessOptions
from .profiles import Profile, ProfileStore
from .translate import TranslationCache, TranslationManager, build_engines
from .translate.base import TranslationResult
from .translate.manager import engine_factories

log = logging.getLogger(__name__)

REGION_ATTR = {"uni": "region_single", "a": "region_a", "b": "region_b"}


class AppController:
    def __init__(self, settings: Optional[Settings] = None, db: Optional[Database] = None,
                 profiles: Optional[ProfileStore] = None, glossary: Optional[Glossary] = None,
                 grabber: Optional[ScreenGrabber] = None):
        self.settings = settings or Settings()
        self._components = None
        try:                                    # pasta de componentes do usuário (opcional; nunca atrapalha o que já funciona)
            from .components.store import get_store, setup_environment
            setup_environment(get_store())
        except Exception:  # noqa: BLE001
            log.warning("pasta de componentes indisponível", exc_info=True)
        self.db = db or Database(paths.database_file())
        self.cache = TranslationCache(self.db)
        self.history = HistoryStore(self.db)
        self.glossary = glossary or Glossary(paths.glossary_file())
        self.profiles = profiles or ProfileStore()
        self.grabber = grabber or ScreenGrabber()
        self.ocr = ocr_mod.OcrRegistry(lambda: self.settings.section("ocr"))
        self.manager = TranslationManager(
            self.cache, lambda: build_engines(self.settings),
            lambda: bool(self.settings.get("translation.cache_only", False)))
        self.pipeline = Pipeline(self.grabber.grab, self.ocr.get_or_fallback, self.translate_pipeline_text,
                                 replace_fn=self.glossary.apply_replacements)
        self.running = False
        self.last_error = ""
        self.last_translation: dict = {}
        self.net = "unknown"            # online | offline | cache | unknown
        self._net_checked = 0.0
        self._started = time.time()
        self.profile: Profile = (self.profiles.load_last() or Profile())
        self.profile.interval = float(self.settings.get("capture.interval", self.profile.interval))
        self._pick_default_engine()
        self.sync()

    def _pick_default_engine(self) -> None:
        """Se o motor do perfil não está utilizável (ex.: sem Tesseract), usa o primeiro disponível."""
        try:
            alt = self.ocr.first_usable(self.profile.ocr_engine)
        except Exception:
            return
        if alt and alt != self.profile.ocr_engine:
            log.info("OCR '%s' indisponível; padrão agora é '%s'", self.profile.ocr_engine, alt)
            self.profile.ocr_engine = alt

    # ------------------------------------------------------------ configuração
    def build_config(self) -> PipelineConfig:
        p, s = self.profile, self.settings
        f = s.section("filters")
        return PipelineConfig(
            channels=p.channels(), interval=p.interval, alphabet=p.alphabet, target=p.target,
            ocr_engine=p.ocr_engine, preprocess=p.preprocess, stable_ms=f["stable_ms"],
            max_wait_ms=f["max_wait_ms"], min_chars=f["min_chars"], min_alnum_ratio=f["min_alnum_ratio"],
            min_confidence=f["min_confidence"], diff_mean=f["diff_mean"], similarity=f["similarity"])

    def sync(self) -> None:
        """Empurra o perfil/configurações atuais para o pipeline."""
        self.pipeline.set_config(self.build_config())

    def apply_profile(self, profile: Profile) -> None:
        self.profile = profile
        self._pick_default_engine()
        self.settings.set("capture.interval", profile.interval, save=False)
        self.sync()
        self.pipeline.refresh("full")              # troca de perfil: novas regiões/idioma/OCR, reprocessa já

    def save_session(self) -> None:
        try:
            self.profiles.save_last(self.profile)
            self.settings.save()
        except OSError as exc:
            log.warning("não salvou a sessão: %s", exc)

    # -- mudanças rápidas (UI)
    def set_region(self, channel: str, bbox) -> bool:
        attr = REGION_ATTR.get(channel)
        if not attr:
            return False
        if bbox is None:
            setattr(self.profile, attr, None)
            self.sync()
            return True
        box = normalize_bbox(bbox)
        if not box:
            return False
        setattr(self.profile, attr, list(box))
        self.sync()
        return True

    def update_profile(self, **kw) -> list[str]:
        """Atualiza campos do perfil atual com validação. Retorna os campos alterados."""
        p = self.profile
        changed = []
        for k, v in kw.items():
            if v is None and k not in ("box_geometry",):
                continue
            if k == "mode":
                p.mode = "dual" if v == "dual" else "single"
            elif k == "alphabet":
                if v not in ALPHABETS:
                    raise ValueError("alfabeto inválido")
                p.alphabet = v
            elif k == "target":
                if v not in dict(TARGET_LANGUAGES):
                    raise ValueError("idioma inválido")
                p.target = v
            elif k == "ocr_engine":
                if v not in ocr_mod.BACKENDS:
                    raise ValueError("motor de OCR desconhecido")
                p.ocr_engine = v
            elif k == "interval":
                p.interval = max(0.2, min(5.0, float(v)))
                self.settings.set("capture.interval", p.interval, save=False)
            elif k == "font_size":
                p.font_size = max(8, min(72, int(v)))
            elif k == "font_family":
                ff = str(v or "default")
                p.font_family = ff if re.fullmatch(r"[a-z0-9_-]{1,32}", ff) else "default"
            elif k == "preprocess":
                merged = p.preprocess.to_dict()
                merged.update(v or {})
                p.preprocess = PreprocessOptions.from_dict(merged)
            elif k == "box_geometry":
                p.box_geometry = str(v or "")
            elif k == "box_open":
                p.box_open = bool(v)
            else:
                continue
            changed.append(k)
        self.sync()
        return changed

    def settings_changed(self, reset_ocr: bool = False, paths: Optional[list] = None) -> None:
        """Aplica configurações e, se o pipeline estiver rodando, reprocessa na hora o que mudou."""
        if reset_ocr:
            self.ocr.reset()
        self.manager.reset_backoff()
        self.sync()
        paths = paths or []
        if reset_ocr or any(p.startswith("ocr.") for p in paths):
            self.pipeline.refresh("full")          # motor/idiomas/GPU do OCR: recaptura e refaz o OCR
        elif any(p.startswith(("translation.", "ai.")) for p in paths):
            self.pipeline.refresh("translate")     # motores, ordem, modo somente-cache, IA: só retraduz

    # ------------------------------------------------------------ componentes (ajuda opcional para instalar itens)
    def components_usage(self) -> dict:
        p, s = self.profile, self.settings
        try:
            hint = ALPHABETS[p.alphabet].hint
        except KeyError:
            hint = "en"
        return {"ocr_engine": p.ocr_engine, "alphabet": p.alphabet, "src_lang": hint, "tgt": p.target,
                "translation_enabled": list(s.get("translation.enabled", []) or []),
                "ai_enabled": bool(s.get("ai.enabled", False)), "ai_provider": s.get("ai.provider", ""),
                "ollama_model": s.get("ai.ollama_model", "")}

    def _components_changed(self, comp_id: str) -> None:
        if comp_id in ("tesseract", "tessdata", "rapidocr", "easyocr", "paddleocr", "winocr", "opencv"):
            self.settings_changed(reset_ocr=True, paths=["ocr.components"])   # reconhece o que acabou de ser instalado
        elif comp_id in ("argos", "ollama", "gemini"):
            self.manager.reset_backoff()

    def components(self):
        if self._components is None:
            from .components.service import ComponentService
            from .components.store import get_store
            self._components = ComponentService(get_store(), get_setting=self.settings.get,
                                                usage=self.components_usage, on_changed=self._components_changed)
        return self._components

    def glossary_changed(self) -> None:
        self.pipeline.refresh("full")              # regras de substituição agem sobre o texto do OCR

    # ------------------------------------------------------------------ ações
    def start(self) -> bool:
        if not self.profile.channels():
            self.last_error = "no_region"
            return False
        self.manager.reset_backoff()
        self.sync()
        ok = self.pipeline.start()
        self.running = self.pipeline.running
        return ok

    def stop(self) -> None:
        self.pipeline.stop()
        self.running = False

    def toggle(self) -> bool:
        if self.pipeline.running:
            self.stop()
            return False
        return self.start()

    def translate_now(self) -> bool:
        if not self.profile.channels():
            self.last_error = "no_region"
            return False
        self.sync()
        self.pipeline.translate_now()
        return True

    def poll_events(self, limit: int = 60, timeout: float = 0.0) -> list[Event]:
        """Remove eventos do pipeline; grava histórico e atualiza estado.

        Com `timeout`, espera até esse tempo pelo primeiro evento (thread do hub).
        """
        events: list[Event] = []
        if timeout > 0:
            import queue as _q
            try:
                events.append(self.pipeline.events.get(timeout=timeout))
            except _q.Empty:
                return events
        events += self.pipeline.drain(limit)
        for ev in events:
            if ev.kind == "translation":
                d = ev.data
                if d.get("ok"):
                    self.last_translation = d
                    if not d.get("cached"):
                        self.net = "online" if self._is_online_engine(d.get("engine", "")) else self.net
                    try:
                        row = self.history.add(d["original"], d["translated"], channel=ev.channel,
                                               src=d.get("src", ""), tgt=d.get("tgt", ""),
                                               engine=d.get("engine", ""), from_cache=bool(d.get("cached")),
                                               profile=self.profile.name)
                        d["history"] = row
                    except Exception:
                        log.exception("falha ao gravar histórico")
                else:
                    self._net_checked = 0.0     # força nova checagem de rede
            elif ev.kind == "state":
                self.running = bool(ev.data.get("running")) and self.pipeline.running
            elif ev.kind == "error":
                self.last_error = ev.data.get("message", "")
        return events

    @staticmethod
    def _is_online_engine(eid: str) -> bool:
        return eid not in ("argos", "")

    # -------------------------------------------------------------- tradução
    def translate_pipeline_text(self, text: str, src: str, tgt: str) -> TranslationResult:
        """Glossário (protege nomes) → cache/cadeia de motores → restaura nomes."""
        prot, mapping = self.glossary.protect(text)
        res = self.manager.translate(prot, src, tgt)
        if res.ok:
            res.text = self.glossary.restore(res.text, mapping)
        return res

    def translate_manual(self, text: str, tgt: str, src: str = "") -> TranslationResult:
        """Tradução da janela manual (detecta o idioma de origem se `src` vazio)."""
        return self.translate_pipeline_text(text, src or detect_any(text), tgt)

    # ------------------------------------------------------------ diagnóstico
    def ocr_self_test(self, engine_id: str, alphabet_key: str = "abc(EN)") -> tuple[bool, str]:
        """Lê uma imagem de exemplo gerada com PIL (usar em thread)."""
        from PIL import Image, ImageDraw, ImageFont
        try:
            backend = self.ocr.get(engine_id)
            if not backend.supports(alphabet_key):
                return False, "motor não suporta esse alfabeto"
            font = None
            for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial.ttf"):
                try:
                    font = ImageFont.truetype(name, 38)
                    break
                except OSError:
                    continue
            font = font or ImageFont.load_default()
            img = Image.new("RGB", (460, 78), (250, 250, 250))
            ImageDraw.Draw(img).text((12, 14), "Hello World 123", font=font, fill=(10, 10, 10))
            from .preprocess import preprocess
            t0 = time.perf_counter()
            res = backend.recognize(preprocess(img, self.profile.preprocess), alphabet_key)
            ms = (time.perf_counter() - t0) * 1000
            ok = "hello" in res.text.lower()
            return ok, f"'{res.text.strip()}'  ({ms:.0f} ms, conf {res.confidence if res.confidence is not None else '-'})"
        except Exception as exc:
            return False, str(exc)

    def check_network(self, force: bool = False) -> str:
        """online | offline | cache. Checa por socket (barato) no máximo a cada 20 s."""
        if self.settings.get("translation.cache_only", False):
            self.net = "cache"
            return self.net
        now = time.monotonic()
        if not force and now - self._net_checked < 20.0 and self.net in ("online", "offline"):
            return self.net
        self._net_checked = now
        for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
            try:
                with socket.create_connection(host, timeout=1.5):
                    self.net = "online"
                    return self.net
            except OSError:
                continue
        self.net = "offline"
        return self.net

    # ---------------------------------------------------------------- estado
    def metrics(self) -> dict:
        st = self.pipeline.last_stats or {}
        stats = dict(self.manager.stats)
        return {
            "running": bool(self.pipeline.running),
            "busy": bool(self.pipeline.busy()),
            "fps": round(float(st.get("fps", 0.0)), 2),
            "ocr_ms": round(float(st.get("ocr_ms", 0.0)), 1),
            "cycle_ms": round(float(st.get("cycle_ms", 0.0)), 1),
            "latency_ms": round(float(self.manager.last_latency_ms), 1),
            "hit_rate": round(self.manager.hit_rate, 3),
            "cache_count": self.cache.count(),
            "stats": stats,
            "ocr_engine": self.profile.ocr_engine,
            "net": self.net,
            "engines": self.manager.engine_status(),
            "uptime": round(time.time() - self._started),
        }

    def translation_engines(self) -> list[dict]:
        """Todos os motores comuns com disponibilidade, ordem e estado de espera."""
        tr = self.settings.section("translation")
        facts = engine_factories(self.settings)
        order = [e for e in tr["order"] if e in facts] + [e for e in facts if e not in tr["order"]]
        status = self.manager.engine_status()
        out = []
        for eid in order:
            try:
                eng = facts[eid]()
                ok, why = eng.available()
                name, online = eng.name, eng.online
            except Exception as exc:
                ok, why, name, online = False, str(exc), eid, True
            stt = status.get(eid, {})
            out.append({"id": eid, "name": name, "online": bool(online), "available": bool(ok), "detail": why,
                        "enabled": eid in tr["enabled"], "cooldown": round(stt.get("cooldown", 0.0)),
                        "error": stt.get("error", "")})
        return out

    def profile_dict(self) -> dict:
        d = self.profile.to_dict()
        d["channels"] = {k: list(v) for k, v in self.profile.channels().items()}
        return d

    def snapshot(self) -> dict:
        from . import APP_AUTHOR, APP_NAME, __version__
        from .config import public_view
        return {
            "app": {"name": APP_NAME, "version": __version__, "author": APP_AUTHOR},
            "profile": self.profile_dict(),
            "profiles": self.profiles.list(),
            "settings": public_view(self.settings),
            "running": bool(self.pipeline.running),
            "ocr": ocr_mod.status(),
            "alphabets": [{"key": a.key, "title": a.title, "tesseract": a.tesseract, "cjk": a.cjk}
                          for a in ALPHABETS.values()],
            "languages": [{"code": c, "name": n} for c, n in TARGET_LANGUAGES],
            "monitors": list_monitors(),
            "engines": self.translation_engines(),
            "metrics": self.metrics(),
        }

    def shutdown(self) -> None:
        try:
            self.pipeline.stop(wait=True)
            self.save_session()
            self.grabber.close()
            self.db.close()
        except Exception:
            log.exception("erro ao encerrar")
