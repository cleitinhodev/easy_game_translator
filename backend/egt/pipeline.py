"""Pipeline de captura → OCR → tradução em threads de trabalho.

As threads NUNCA tocam em widgets: tudo vai para `events` (queue.Queue) e a UI lê com after().
Worker threads never touch widgets; they post Event objects to a queue polled by the UI.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

from PIL import Image

from .change import ImageChangeDetector, TextStabilizer, is_garbage, texts_similar
from .languages import alphabet, clean_ocr_text, detect_source, smart_join_lines
from .preprocess import PreprocessOptions, preprocess

log = logging.getLogger(__name__)


@dataclass
class Event:
    kind: str                 # ocr | empty | translation | stats | error | state | info
    channel: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class PipelineConfig:
    channels: dict = field(default_factory=dict)      # {'uni': (x1,y1,x2,y2)} ou {'a':..., 'b':...}
    interval: float = 1.0
    alphabet: str = "abc(EN)"
    target: str = "pt"
    ocr_engine: str = "tesseract"
    preprocess: PreprocessOptions = field(default_factory=PreprocessOptions)
    stable_ms: int = 450
    max_wait_ms: int = 4000
    min_chars: int = 3
    min_alnum_ratio: float = 0.5
    min_confidence: float = 35.0
    diff_mean: float = 1.0
    similarity: float = 0.96
    detect_source: bool = True
    join_lines: bool = True


PREVIEW_MAX_W = 480
PREVIEW_QUALITY = 70


def make_preview(img: Image.Image, max_w: int = PREVIEW_MAX_W, quality: int = PREVIEW_QUALITY) -> dict:
    """Miniatura leve (JPEG q70, ≤480 px de largura) da região capturada, como data URL."""
    import base64
    import io
    im = img.convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, max(1, round(im.height * max_w / im.width))))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return {"image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            "width": img.width, "height": img.height}


@dataclass
class _Job:
    channel: str
    text: str
    cfg: PipelineConfig
    attempt: int = 0
    gen: int = 0              # geração do pipeline quando o job foi criado (refresh descarta jobs antigos)


class _Channel:
    def __init__(self, cfg: PipelineConfig):
        self.bbox: Optional[tuple] = None
        self.det = ImageChangeDetector(mean_thr=cfg.diff_mean)
        self.stab = TextStabilizer(cfg.stable_ms, cfg.max_wait_ms, cfg.similarity)
        self.last_text = ""
        self.had_text = False
        self.preview_seq = 0


class Pipeline:
    """
    capture_fn(bbox) -> PIL.Image
    ocr_provider(engine_id) -> backend com .recognize(img, alphabet) -> OcrResult
    translate_fn(text, src, tgt) -> TranslationResult  (já com glossário/cache/cadeia)
    replace_fn(text) -> text   (regras de substituição do OCR)
    """

    def __init__(self, capture_fn: Callable, ocr_provider: Callable, translate_fn: Callable,
                 replace_fn: Callable[[str], str] = lambda t: t,
                 config: Optional[PipelineConfig] = None, clock: Callable[[], float] = time.monotonic):
        self.capture_fn = capture_fn
        self.ocr_provider = ocr_provider
        self.translate_fn = translate_fn
        self.replace_fn = replace_fn
        self._cfg = config or PipelineConfig()
        self._clock = clock
        self.events: "queue.Queue[Event]" = queue.Queue()
        self._lock = threading.Lock()
        self._run: Optional["_Run"] = None
        self._err_seen: dict[str, float] = {}
        self.last_stats: dict[str, Any] = {}
        self._gen = 0

    # ---------------------------------------------------------------- config
    @property
    def config(self) -> PipelineConfig:
        return self._cfg

    # campos que mudam o que se lê da imagem → recapturar + refazer o OCR
    _FULL_FIELDS = ("alphabet", "ocr_engine", "preprocess", "min_chars", "min_alnum_ratio", "min_confidence")

    def set_config(self, cfg: PipelineConfig) -> None:
        """Troca atômica (as threads releem a cada ciclo).

        Com o pipeline rodando, mudanças que afetam a saída forçam o reprocessamento imediato,
        mesmo que a imagem/texto não tenham mudado: idioma de destino → só retraduz o último texto;
        OCR/alfabeto/pré-processamento/filtros → recaptura e refaz o OCR.
        """
        old, self._cfg = self._cfg, cfg
        if any(getattr(old, f) != getattr(cfg, f) for f in self._FULL_FIELDS):
            self.refresh("full")
        elif old.target != cfg.target:
            self.refresh("translate")

    def refresh(self, mode: str = "full") -> bool:
        """Reprocessa já, ignorando a detecção de mudança. mode: 'translate' | 'full'.

        Só tem efeito no modo contínuo. Traduções em andamento com a configuração antiga são descartadas.
        """
        with self._lock:
            run = self._run
            if not (run and run.continuous and run.capture_thread.is_alive() and not run.stop.is_set()):
                return False
            self._gen += 1
            run.request_refresh(mode)
        return True

    def update_config(self, **kw) -> None:
        self._cfg = replace(self._cfg, **kw)

    # ---------------------------------------------------------------- estado
    @property
    def running(self) -> bool:
        r = self._run
        return bool(r and r.continuous and r.capture_thread.is_alive() and not r.stop.is_set())

    def busy(self) -> bool:
        r = self._run
        return bool(r and r.capture_thread.is_alive())

    def start(self) -> bool:
        """Inicia o modo contínuo. Retorna False se já estiver rodando."""
        with self._lock:
            if self.running:
                return False
            self._stop_current()
            self._run = _Run(self, continuous=True)
            self._run.begin()
        self._post("state", data={"running": True})
        return True

    def stop(self, wait: bool = False) -> None:
        with self._lock:
            run = self._run
            self._stop_current()
        if wait and run:
            run.join(2.0)

    def _stop_current(self) -> None:
        if self._run:
            self._run.stop.set()
            self._run.wake.set()
            self._run.jobs.put(None)

    def translate_now(self) -> None:
        """Captura + OCR + tradução uma única vez (ignora detecção de mudança e debounce)."""
        with self._lock:
            run = self._run
            if run and run.continuous and run.capture_thread.is_alive() and not run.stop.is_set():
                run.force.set()
                run.wake.set()
                return
            self._stop_current()
            self._run = _Run(self, continuous=False)
            self._run.begin()
        self._post("state", data={"running": False, "single_shot": True})

    # ------------------------------------------------------------ utilidades
    def _post(self, kind: str, channel: str = "", data: Optional[dict] = None) -> None:
        self.events.put(Event(kind, channel, data or {}))

    def _post_error(self, msg: str, key: str = "") -> None:
        now = self._clock()
        key = key or msg
        if now - self._err_seen.get(key, -99.0) > 5.0:   # evita enxurrada da mesma mensagem
            self._err_seen[key] = now
            self._post("error", data={"message": msg})

    def drain(self, limit: int = 100) -> list[Event]:
        """Para a UI/testes: remove até `limit` eventos da fila."""
        out = []
        for _ in range(limit):
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out


class _Run:
    """Uma execução (contínua ou de um disparo) com suas duas threads."""

    def __init__(self, p: Pipeline, continuous: bool):
        self.p = p
        self.continuous = continuous
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.force = threading.Event()
        self.jobs: "queue.Queue[Optional[_Job]]" = queue.Queue()
        self.channels: dict[str, _Channel] = {}
        self.retry: dict[str, tuple[_Job, float]] = {}
        self._refresh = ""
        self._rlock = threading.Lock()
        self.pending_jobs = 0
        self._plock = threading.Lock()
        self.capture_thread = threading.Thread(target=self._capture_loop, name="egt-capture", daemon=True)
        self.translate_thread = threading.Thread(target=self._translate_loop, name="egt-translate", daemon=True)
        self._fps_t = p._clock()
        self._fps_n = 0
        self._ocr_ms = 0.0
        self._cycle_ms = 0.0

    def request_refresh(self, mode: str) -> None:
        with self._rlock:
            if mode == "full" or self._refresh != "full":
                self._refresh = "full" if mode == "full" else "translate"
        self.retry.clear()
        self.wake.set()

    def _pop_refresh(self) -> str:
        with self._rlock:
            m, self._refresh = self._refresh, ""
        return m

    def begin(self) -> None:
        self.translate_thread.start()
        self.capture_thread.start()

    def join(self, timeout: float) -> None:
        self.capture_thread.join(timeout)
        self.translate_thread.join(timeout)

    # ---------------------------------------------------------- captura / OCR
    def _capture_loop(self) -> None:
        p = self.p
        try:
            first = True
            while not self.stop.is_set():
                t0 = p._clock()
                cfg = p._cfg
                force = first and not self.continuous or self.force.is_set()
                self.force.clear()
                refresh = self._pop_refresh()
                if refresh == "translate" and not self._retranslate(cfg):
                    refresh = "full"            # nada lido ainda: precisa do OCR
                if refresh == "full":
                    force = True
                    self._announce_pending(cfg)
                try:
                    self._cycle(cfg, force)
                except Exception as exc:    # nunca mata a thread
                    log.exception("erro no ciclo")
                    p._post_error(f"{type(exc).__name__}: {exc}")
                first = False
                self._cycle_ms = (p._clock() - t0) * 1000
                self._stats()
                if not self.continuous:
                    break
                remaining = max(0.02, cfg.interval - (p._clock() - t0))
                self.wake.wait(remaining)
                self.wake.clear()
        finally:
            if not self.continuous:
                self._wait_jobs()
                self.jobs.put(None)
            else:
                self.jobs.put(None)
            self.stop.set()
            if p._run is self:          # um run antigo não deve sobrescrever o estado do novo
                p._post("state", data={"running": False})

    def _wait_jobs(self, timeout: float = 90.0) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end and not self.stop_requested_hard():
            with self._plock:
                if self.pending_jobs <= 0:
                    return
            time.sleep(0.05)

    def stop_requested_hard(self) -> bool:
        return False

    def _announce_pending(self, cfg: PipelineConfig, only_with_text: bool = False) -> None:
        for name in cfg.channels:
            st = self.channels.get(name)
            if only_with_text and not (st and st.last_text):
                continue
            self.p._post("pending", name, {"phase": "translating", "target": cfg.target})

    def _retranslate(self, cfg: PipelineConfig) -> bool:
        """Retraduz o último texto lido de cada canal (sem recapturar). False se nenhum canal tem texto."""
        names = [n for n in cfg.channels if (n in self.channels and self.channels[n].last_text)]
        if not names:
            return False
        for n in names:
            st = self.channels[n]
            st.stab.pending = None
            st.stab.last_emitted = st.last_text
            self.p._post("pending", n, {"phase": "translating", "target": cfg.target})
            self._enqueue(n, st.last_text, cfg)
        return True

    def _state(self, name: str, cfg: PipelineConfig) -> _Channel:
        st = self.channels.get(name)
        if st is None:
            st = self.channels[name] = _Channel(cfg)
        st.det.mean_thr = cfg.diff_mean
        st.stab.stable_s = max(0, cfg.stable_ms) / 1000.0
        st.stab.max_wait_s = max(st.stab.stable_s, cfg.max_wait_ms / 1000.0)
        st.stab.similarity = cfg.similarity
        return st

    def _cycle(self, cfg: PipelineConfig, force: bool) -> None:
        p = self.p
        if not cfg.channels:
            p._post_error("Nenhuma região de captura definida.", "noregion")
            return
        for name in list(self.channels):
            if name not in cfg.channels:
                del self.channels[name]
        self._do_retries()
        ocr_total = 0.0
        for name, bbox in cfg.channels.items():
            if self.stop.is_set():
                return
            st = self._state(name, cfg)
            if st.bbox != tuple(bbox):          # região mudou: zera o estado
                st.bbox = tuple(bbox)
                st.det.reset()
                st.stab.reset(forget_last=True)
                st.last_text = ""
            if force:
                st.det.reset()
            ocr_total += self._channel(name, st, cfg, force)
        if ocr_total:
            self._ocr_ms = ocr_total      # guarda o último OCR real (ciclos sem mudança custam 0)

    def _channel(self, name: str, st: _Channel, cfg: PipelineConfig, force: bool) -> float:
        p = self.p
        try:
            img: Image.Image = p.capture_fn(st.bbox)
        except Exception as exc:
            p._post_error(f"Falha na captura: {exc}", "capture")
            return 0.0
        now = p._clock()
        if not force and not st.det.changed(img):
            ready = st.stab.poll(now)       # imagem igual: só deixa o texto pendente "envelhecer"
            if ready:
                self._enqueue(name, ready, cfg)
            return 0.0
        pre = preprocess(img, cfg.preprocess)
        preview_sent = False
        try:
            backend = p.ocr_provider(cfg.ocr_engine)
            if hasattr(backend, "supports") and not backend.supports(cfg.alphabet):
                p._post_error("O motor de OCR escolhido não suporta esse alfabeto.", "unsupported")
                return 0.0
            res = backend.recognize(pre, cfg.alphabet)
            self._post_preview(name, st, img)       # a miniatura acompanha o resultado do OCR (mesma captura)
            preview_sent = True
        except Exception as exc:
            if not preview_sent:
                self._post_preview(name, st, img)
            msg = str(exc) or type(exc).__name__
            if type(exc).__name__ != "OcrError":
                log.exception("OCR falhou")
            p._post_error(msg, "ocr")
            st.det.reset()                  # tenta de novo no próximo ciclo
            return 0.0
        text = p.replace_fn(clean_ocr_text(res.text, cfg.alphabet))
        min_chars = 1 if alphabet(cfg.alphabet).cjk else cfg.min_chars
        low_conf = (res.confidence is not None and res.confidence < cfg.min_confidence)
        if is_garbage(text, min_chars, cfg.min_alnum_ratio) or (low_conf and not force):
            st.stab.reset(forget_last=True)
            if st.had_text or force:
                st.had_text = False
                st.last_text = ""
                p._post("empty", name, {"confidence": res.confidence, "text": text})
            return res.elapsed_ms
        st.had_text = True
        if not texts_similar(text, st.last_text, 1.0):
            st.last_text = text
            p._post("ocr", name, {"text": text, "confidence": res.confidence,
                                  "engine": res.engine, "ms": res.elapsed_ms})
        if force:
            st.stab.pending = None
            st.stab.last_emitted = text
            self._enqueue(name, text, cfg)
        else:
            ready = st.stab.feed(text, now)
            if ready:
                self._enqueue(name, ready, cfg)
        return res.elapsed_ms

    def _post_preview(self, name: str, st: _Channel, img: Image.Image) -> None:
        """Toda vez que a imagem mudou (ou num refresh forçado) envia uma miniatura nova, mesmo que o texto não mude."""
        if not getattr(self.p, "emit_preview", True):
            return
        try:
            payload = make_preview(img)
        except Exception:
            log.exception("falha ao gerar miniatura")
            return
        st.preview_seq += 1
        payload["seq"] = st.preview_seq
        self.p._post("preview", name, payload)

    # ----------------------------------------------------------- tradução
    def _enqueue(self, name: str, text: str, cfg: PipelineConfig, attempt: int = 0) -> None:
        with self._plock:
            self.pending_jobs += 1
        self.jobs.put(_Job(name, text, cfg, attempt, self.p._gen))

    def _do_retries(self) -> None:
        now = self.p._clock()
        for name, (job, due) in list(self.retry.items()):
            if now >= due:
                del self.retry[name]
                st = self.channels.get(name)
                if st is not None and texts_similar(st.stab.last_emitted or "", job.text, 0.98):
                    self._enqueue(name, job.text, self.p._cfg, job.attempt)

    def _translate_loop(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                break
            # só a tradução mais nova de cada canal importa
            batch = {job.channel: job}
            skipped = 0
            while True:
                try:
                    nxt = self.jobs.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    self.jobs.put(None)
                    break
                if nxt.channel in batch:
                    skipped += 1
                batch[nxt.channel] = nxt
            for j in batch.values():
                self._translate(j)
            with self._plock:
                self.pending_jobs -= len(batch) + skipped
            if self.stop.is_set() and self.jobs.empty():
                break

    def _translate(self, job: _Job) -> None:
        p = self.p
        cfg = job.cfg
        try:
            src_text = smart_join_lines(job.text, alphabet(cfg.alphabet).cjk) if cfg.join_lines else job.text
            src = detect_source(src_text, cfg.alphabet) if cfg.detect_source else alphabet(cfg.alphabet).hint
            res = p.translate_fn(src_text, src, cfg.target)
        except Exception as exc:
            log.exception("erro ao traduzir")
            p._post_error(f"Tradução: {type(exc).__name__}: {exc}", "translate")
            return
        if job.gen != p._gen:           # a configuração mudou durante a tradução: resultado velho, descarta
            return
        if not res.ok:
            p._post_error(res.error or "falha na tradução", "translate")
            if job.attempt < 3 and self.continuous and not self.stop.is_set():
                job.attempt += 1
                self.retry[job.channel] = (job, p._clock() + 2.0 * (2 ** job.attempt))
            p._post("translation", job.channel, {"original": job.text, "translated": "", "ok": False,
                                                 "error": res.error, "engine": res.engine, "src": src,
                                                 "tgt": cfg.target, "cached": False})
            return
        p._post("translation", job.channel, {
            "original": job.text, "translated": res.text, "ok": True, "engine": res.engine,
            "cached": res.cached, "src": res.src or src, "tgt": cfg.target, "ms": res.elapsed_ms})

    def _stats(self) -> None:
        p = self.p
        self._fps_n += 1
        now = p._clock()
        dt = now - self._fps_t
        if dt >= 1.0:
            fps = self._fps_n / dt
            self._fps_t, self._fps_n = now, 0
            p.last_stats = {"fps": fps, "ocr_ms": self._ocr_ms, "cycle_ms": self._cycle_ms}
            p._post("stats", data=dict(p.last_stats))
