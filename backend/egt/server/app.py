"""API HTTP + WebSocket do backend (FastAPI). Só escuta em 127.0.0.1 e exige o token da sessão."""
from __future__ import annotations

import asyncio
import base64
import importlib
import io
import json
import logging
import os
import platform
import secrets
import tempfile
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from .. import APP_AUTHOR, APP_NAME, __version__, logsetup, paths
from .. import ocr as ocr_mod
from ..app import AppController
from ..capture.screen import list_monitors, normalize_bbox
from ..config import apply_changes, public_view
from ..languages import ALPHABETS
from ..ocr.tesseract import TesseractBackend, find_tesseract
from ..preprocess import preprocess
from ..profiles import Profile
from .hub import EventHub

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
ALLOWED_ORIGIN_RE = r"^(null|file://|egt://app|http://(127\.0\.0\.1|localhost)(:\d+)?)$"


# ------------------------------------------------------------------ modelos
class ProfilePatch(BaseModel):
    mode: Optional[str] = None
    alphabet: Optional[str] = None
    target: Optional[str] = None
    ocr_engine: Optional[str] = None
    interval: Optional[float] = None
    font_size: Optional[int] = None
    font_family: Optional[str] = None
    preprocess: Optional[dict] = None
    box_geometry: Optional[str] = None
    box_open: Optional[bool] = None


class RegionBody(BaseModel):
    channel: str
    bbox: Optional[list[float]] = None


class SettingsPatch(BaseModel):
    changes: dict[str, Any]


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class OcrTestBody(BaseModel):
    engine: str
    alphabet: Optional[str] = None


class PreviewBody(BaseModel):
    channel: Optional[str] = None
    bbox: Optional[list[float]] = None
    processed: bool = False
    read: bool = False
    max_width: int = 720


class ManualBody(BaseModel):
    text: str = Field(max_length=5000)
    tgt: str
    src: str = ""


class TtsBody(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    lang: str = "en"


class TestTranslationBody(BaseModel):
    text: str = "Hello world, this is a test."
    src: str = "en"
    tgt: str = "pt"


class EngineTestBody(BaseModel):
    engine: str = Field(pattern=r"^[a-z0-9_]{2,20}$")
    text: str = Field(default="Hello, adventurer! The gate is closed.", min_length=1, max_length=2000)
    src: str = Field(default="", max_length=12)
    tgt: str = Field(default="pt", min_length=2, max_length=12)


class ArgosBody(BaseModel):
    src: str
    tgt: str


class CompItemBody(BaseModel):
    item: str = Field(default="", max_length=80)
    confirmed: bool = False


class CompLocationBody(BaseModel):
    id: str = Field(max_length=40)                      # id do componente ou 'root'
    path: str = Field(default="", max_length=1024)
    copy_existing: bool = False
    reset: bool = False


class CompPathBody(BaseModel):
    path: str = Field(default="", max_length=1024)
    confirmed: bool = False


class CompDemoBody(BaseModel):
    offline: Optional[bool] = None
    python: Optional[bool] = None
    ollama: Optional[bool] = None


class AiTestBody(BaseModel):
    provider: str = Field(default="", pattern="^(|gemini|ollama)$")
    model: str = Field(default="", max_length=120)          # opcional: testar um modelo sem salvar
    url: str = Field(default="", max_length=300)            # opcional (Ollama)


class OllamaStatusBody(BaseModel):
    url: str = Field(default="", max_length=300)


class SecretRemoveBody(BaseModel):
    path: str = Field(max_length=64)
    confirmed: bool = False


class EnvRemoveBody(BaseModel):
    name: str = Field(max_length=64)
    confirmed: bool = False


class GlossaryBody(BaseModel):
    rules: list[dict] = []
    keep: list[str] = []


class GlossaryTestBody(BaseModel):
    text: str


def _data_url(img, fmt: str = "PNG", quality: int = 82) -> str:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=quality)
        mime = "image/jpeg"
    else:
        img.save(buf, "PNG", optimize=False)
        mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def _shrink(img, max_w: int):
    if img.width > max_w:
        r = max_w / img.width
        img = img.resize((max_w, max(1, int(img.height * r))))
    return img


def create_app(ctrl: AppController, token: str, hub: Optional[EventHub] = None,
               allow_dev_origin: bool = True) -> FastAPI:
    hub = hub or EventHub(ctrl)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.start(asyncio.get_running_loop())
        try:
            yield
        finally:
            hub.stop()
            ctrl.shutdown()

    app = FastAPI(title="EGT backend", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctrl, app.state.hub, app.state.token = ctrl, hub, token
    app.state.server = None

    # ---------------------------------------------------------------- segurança
    def host_ok(host_header: str) -> bool:
        host = (host_header or "").rsplit(":", 1)[0] if not host_header.startswith("[") else host_header.split("]")[0] + "]"
        return host in LOCAL_HOSTS

    @app.middleware("http")
    async def _host_guard(request: Request, call_next):
        # defesa contra DNS rebinding: só aceita Host local
        if not host_ok(request.headers.get("host", "")):
            return Response("host inválido", status_code=400)
        return await call_next(request)

    app.add_middleware(CORSMiddleware, allow_origin_regex=ALLOWED_ORIGIN_RE, allow_methods=["*"],
                       allow_headers=["x-egt-token", "content-type"], max_age=600)

    def require_token(x_egt_token: Optional[str] = Header(default=None), token_q: Optional[str] = Query(
            default=None, alias="token")) -> None:
        sent = x_egt_token or token_q or ""
        if not secrets.compare_digest(sent.encode(), token.encode()):
            raise HTTPException(status_code=401, detail="token inválido")

    api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

    def broadcast_profile() -> None:
        hub.publish({"type": "profile", "data": ctrl.profile_dict()})

    def broadcast_settings() -> None:
        hub.publish({"type": "settings", "data": public_view(ctrl.settings)})

    # ---------------------------------------------------------------- estado
    @api.get("/health")
    def health():
        return {"ok": True, "version": __version__, "app": APP_NAME, "pid": os.getpid()}

    @api.get("/state")
    def state():
        return ctrl.snapshot()

    @api.get("/metrics")
    def metrics():
        return ctrl.metrics()

    @api.get("/monitors")
    def monitors():
        return list_monitors()

    @api.post("/shutdown")
    def shutdown():
        srv = app.state.server
        if srv is not None:
            srv.should_exit = True
        else:  # pragma: no cover
            asyncio.get_event_loop().call_later(0.2, os._exit, 0)
        return {"ok": True}

    # ---------------------------------------------------------------- pipeline
    def _action_result(ok: bool) -> dict:
        err = "" if ok else (ctrl.last_error or "")
        return {"ok": bool(ok), "running": bool(ctrl.pipeline.running), "error": err}

    @api.post("/pipeline/start")
    def p_start():
        ctrl.last_error = ""
        return _action_result(ctrl.start() or ctrl.pipeline.running)

    @api.post("/pipeline/stop")
    def p_stop():
        ctrl.stop()
        return _action_result(True)

    @api.post("/pipeline/toggle")
    def p_toggle():
        ctrl.last_error = ""
        if ctrl.pipeline.running:
            ctrl.stop()
            return _action_result(True)
        return _action_result(ctrl.start())

    @api.post("/pipeline/translate-now")
    def p_now():
        ctrl.last_error = ""
        return _action_result(ctrl.translate_now())

    # ---------------------------------------------------------------- perfil
    @api.get("/profile")
    def get_profile():
        return ctrl.profile_dict()

    @api.patch("/profile")
    def patch_profile(body: ProfilePatch):
        fields = body.model_dump(exclude_unset=True)
        try:
            changed = ctrl.update_profile(**fields)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc))
        broadcast_profile()
        return {"changed": changed, "profile": ctrl.profile_dict()}

    @api.post("/profile/region")
    def set_region(body: RegionBody):
        if body.channel not in ("uni", "a", "b"):
            raise HTTPException(422, "canal inválido")
        if body.bbox is not None and normalize_bbox(body.bbox) is None:
            raise HTTPException(422, "região inválida (mínimo 4×4 px)")
        ctrl.set_region(body.channel, body.bbox)
        broadcast_profile()
        return {"profile": ctrl.profile_dict()}

    @api.get("/profiles")
    def list_profiles():
        return ctrl.profiles.list()

    @api.post("/profiles")
    def save_profile(body: NameBody):
        ctrl.profile.name = body.name.strip()
        ctrl.profiles.save(ctrl.profile)
        ctrl.save_session()
        broadcast_profile()
        hub.publish({"type": "profiles", "data": ctrl.profiles.list()})
        return {"ok": True, "profiles": ctrl.profiles.list(), "profile": ctrl.profile_dict()}

    @api.post("/profiles/load")
    def load_profile(body: NameBody):
        prof = ctrl.profiles.load(body.name)
        if prof is None:
            raise HTTPException(404, "perfil não encontrado")
        was_running = ctrl.pipeline.running
        ctrl.apply_profile(prof)
        broadcast_profile()
        return {"ok": True, "profile": ctrl.profile_dict(), "running": was_running}

    @api.delete("/profiles")
    def delete_profile(name: str = Query(min_length=1)):
        ok = ctrl.profiles.delete(name)
        hub.publish({"type": "profiles", "data": ctrl.profiles.list()})
        return {"ok": ok, "profiles": ctrl.profiles.list()}

    # ---------------------------------------------------------------- configurações
    @api.get("/settings")
    def get_settings():
        return public_view(ctrl.settings)

    @api.patch("/settings")
    def patch_settings(body: SettingsPatch):
        try:
            changed = apply_changes(ctrl.settings, body.changes)
        except KeyError as exc:
            raise HTTPException(422, f"configuração desconhecida: {exc.args[0]}")
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        if "capture.interval" in changed:
            ctrl.profile.interval = float(ctrl.settings.get("capture.interval"))
            broadcast_profile()
        ctrl.settings_changed(reset_ocr=any(p.startswith("ocr.") for p in changed), paths=changed)
        broadcast_settings()
        if any(p.startswith(("translation.", "ai.")) for p in changed):
            hub.publish({"type": "engines", "data": ctrl.translation_engines()})
        return {"changed": changed, "settings": public_view(ctrl.settings)}

    # ---------------------------------------------------------------- OCR
    @api.get("/ocr/engines")
    def ocr_engines():
        import importlib as _il
        _il.invalidate_caches()
        out = ocr_mod.status()
        for e in out:   # Tesseract só conta como instalado se o executável também existir
            if e["id"] == "tesseract" and e["available"]:
                exe = ocr_mod.find_tesseract(ctrl.settings.get("ocr.tesseract_path", "") or "")
                if exe is None:
                    e["available"], e["detail"] = False, "pytesseract ok, mas o executável do Tesseract não foi encontrado"
        return out

    @api.post("/ocr/test")
    def ocr_test(body: OcrTestBody):
        if body.engine not in ocr_mod.BACKENDS:
            raise HTTPException(422, "motor desconhecido")
        ok, msg = ctrl.ocr_self_test(body.engine, body.alphabet or ctrl.profile.alphabet)
        return {"ok": ok, "message": msg}

    @api.get("/ocr/tesseract")
    def tesseract_info():
        path = find_tesseract(ctrl.settings.get("ocr.tesseract_path", ""))
        if not path:
            return {"found": False, "path": "", "version": "", "langs": [], "missing": []}
        try:
            be = TesseractBackend({"tesseract_path": path})
            langs = sorted(be.installed_languages() - {"osd"})
            wanted = sorted({a.tesseract for a in ALPHABETS.values()} - set(langs))
            return {"found": True, "path": path, "version": be.version(), "langs": langs, "missing": wanted}
        except Exception as exc:
            return {"found": True, "path": path, "version": "", "langs": [], "missing": [], "error": str(exc)}

    @api.post("/capture/preview")
    def capture_preview(body: PreviewBody):
        bbox = body.bbox or ctrl.profile.channels().get(body.channel or next(iter(ctrl.profile.channels()), "uni"))
        if not bbox:
            raise HTTPException(409, "no_region")
        try:
            img = ctrl.grabber.grab(bbox)
        except Exception as exc:
            raise HTTPException(500, f"falha na captura: {exc}")
        out: dict[str, Any] = {"width": img.width, "height": img.height,
                               "image": _data_url(_shrink(img, body.max_width), "JPEG")}
        if body.processed or body.read:
            pre = preprocess(img, ctrl.profile.preprocess)
            out["processed"] = _data_url(_shrink(pre, body.max_width))
            if body.read:
                try:
                    res = ctrl.ocr.get_or_fallback(ctrl.profile.ocr_engine).recognize(pre, ctrl.profile.alphabet)
                    out["text"] = res.text
                    out["confidence"] = res.confidence
                    out["ms"] = round(res.elapsed_ms)
                except Exception as exc:
                    out["error"] = str(exc)
        return out

    # ---------------------------------------------------------------- tradução
    @api.get("/translation/engines")
    def tr_engines():
        return ctrl.translation_engines()

    @api.post("/translation/test")
    def tr_test(body: TestTranslationBody):
        res = ctrl.manager.translate(body.text, body.src, body.tgt)
        return {"ok": res.ok, "text": res.text, "engine": res.engine, "cached": res.cached,
                "error": res.error, "ms": round(res.elapsed_ms), "attempts": res.attempts, "codes": res.codes}

    @api.post("/translation/engine_test")
    def tr_engine_test(body: EngineTestBody):
        """Testa UM tradutor (online? + tradução manual do texto de exemplo). Não usa nem grava o cache."""
        res = ctrl.test_engine(body.engine, body.text, body.src.strip(), body.tgt.strip())
        hub.publish({"type": "engines", "data": ctrl.translation_engines()})
        return res

    @api.get("/cache")
    def cache_info():
        return {"count": ctrl.cache.count(), "hit_rate": ctrl.manager.hit_rate, "stats": ctrl.manager.stats}

    @api.delete("/cache")
    def cache_clear():
        ctrl.cache.clear()
        return {"ok": True, "count": ctrl.cache.count()}

    @api.get("/argos")
    def argos_info():
        from ..translate import argos
        pairs = argos.installed_pairs()
        return {"installed": argos.module_present(), "pairs": [list(p) for p in pairs]}

    @api.post("/argos/install")
    def argos_install(body: ArgosBody):
        from ..translate import argos
        if not argos.module_present():
            raise HTTPException(409, "argostranslate não instalado (pip install argostranslate)")
        try:
            msg = argos.install_pair(body.src, body.tgt)
        except Exception as exc:
            raise HTTPException(502, str(exc))
        return {"ok": True, "message": msg}

    @api.post("/translate/manual")
    def translate_manual(body: ManualBody):
        text = body.text.strip()
        if not text:
            return {"ok": True, "text": "", "engine": "", "cached": False, "ms": 0}
        res = ctrl.translate_manual(text, body.tgt, body.src)
        return {"ok": res.ok, "text": res.text, "engine": res.engine, "cached": res.cached,
                "error": res.error, "ms": round(res.elapsed_ms), "src": res.src}

    @api.post("/tts")
    def tts(body: TtsBody):
        try:
            from gtts import gTTS
        except ImportError:
            raise HTTPException(501, "instale: pip install gTTS")
        buf = io.BytesIO()
        try:
            gTTS(text=body.text, lang=body.lang).write_to_fp(buf)
        except Exception as exc:
            raise HTTPException(502, f"falha na narração: {type(exc).__name__}: {exc}")
        return Response(buf.getvalue(), media_type="audio/mpeg")

    @api.post("/stt")
    async def stt(request: Request, lang: str = Query(default="pt-BR")):
        data = await request.body()
        if not data:
            raise HTTPException(400, "áudio vazio")

        def work() -> str:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.AudioFile(io.BytesIO(data)) as source:
                audio = r.record(source)
            return r.recognize_google(audio, language=lang)

        try:
            text = await asyncio.get_running_loop().run_in_executor(None, work)
        except ImportError:
            raise HTTPException(501, "instale: pip install SpeechRecognition")
        except Exception as exc:
            name = type(exc).__name__
            raise HTTPException(422 if name == "UnknownValueError" else 502, name)
        return {"text": text}

    # ---------------------------------------------------------------- glossário
    @api.get("/glossary")
    def get_glossary():
        return {"rules": ctrl.glossary.rules, "keep": ctrl.glossary.keep}

    @api.put("/glossary")
    def put_glossary(body: GlossaryBody):
        ctrl.glossary.set_data(body.rules, body.keep)
        ctrl.glossary_changed()
        return {"rules": ctrl.glossary.rules, "keep": ctrl.glossary.keep}

    @api.post("/glossary/test")
    def test_glossary(body: GlossaryTestBody):
        replaced = ctrl.glossary.apply_replacements(body.text)
        protected, mapping = ctrl.glossary.protect(replaced)
        return {"replaced": replaced, "protected": protected, "terms": len(mapping)}

    # ---------------------------------------------------------------- IA
    @api.post("/ai/test")
    def ai_test(body: Optional[AiTestBody] = None):
        """Testa UMA IA (a escolhida em `provider`, mesmo que não seja a selecionada). Não salva nada."""
        from ..translate.ai import AiError, GeminiTranslate, OllamaTranslate
        from ..translate.base import RateLimited
        body = body or AiTestBody()
        prov = body.provider or ctrl.settings.get("ai.mode", "off")
        ai = ctrl.settings.section("ai")
        ctx = lambda: ctrl.settings.get("ai.context", "")  # noqa: E731
        if prov == "gemini":
            if ctrl.settings.secret_state("ai.gemini_key") == "unreadable" and not ctrl.settings.gemini_key():
                return {"ok": False, "code": "key_unreadable", "provider": prov,
                        "message": "A chave salva não pode ser lida neste computador. Cole a chave novamente."}
            eng = GeminiTranslate(ctrl.settings.gemini_key, (body.model or ai.get("gemini_model") or "").strip(), ctx)
        elif prov == "ollama":
            eng = OllamaTranslate((body.url or ai.get("ollama_url") or "").strip(), (body.model or ai.get("ollama_model") or "").strip(), ctx)
        else:
            return {"ok": False, "code": "off", "provider": "off", "message": "IA desligada"}
        ok, why = eng.available()
        if not ok:
            return {"ok": False, "code": "no_key" if prov == "gemini" else "config", "provider": prov, "message": why}
        t0 = time.perf_counter()
        try:
            out = eng.translate("Hello, adventurer! The gate is closed.", "en", ctrl.profile.target)
            return {"ok": True, "message": out, "ms": round((time.perf_counter() - t0) * 1000), "engine": eng.id, "provider": prov}
        except (AiError, RateLimited) as exc:
            code = getattr(exc, "code", "rate_limit" if isinstance(exc, RateLimited) else "http")
            return {"ok": False, "code": code, "provider": prov, "message": str(exc), "model": eng.model}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "code": "http", "provider": prov, "message": type(exc).__name__}

    @api.post("/ai/ollama/status")
    def ollama_status(body: Optional[OllamaStatusBody] = None):
        """Servidor Ollama rodando? + modelos instalados (GET /api/tags). Só http(s); sem seguir redirecionamentos."""
        import urllib.parse
        import requests
        url = ((body.url if body else "") or ctrl.settings.get("ai.ollama_url", "") or "http://localhost:11434").strip().rstrip("/")
        u = urllib.parse.urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return {"server": False, "models": [], "error": "url"}
        try:
            r = requests.get(url + "/api/tags", timeout=2.5, allow_redirects=False)
            if r.status_code != 200:
                return {"server": False, "models": [], "error": f"HTTP {r.status_code}"}
            models = sorted({str(m.get("name") or m.get("model") or "") for m in (r.json().get("models") or []) if isinstance(m, dict)} - {""})
            return {"server": True, "models": models[:200]}
        except (requests.RequestException, ValueError, AttributeError):
            return {"server": False, "models": [], "error": "down"}

    # ---------------------------------------------------------------- chaves (segredos)
    @api.post("/secrets/remove")
    def secret_remove(body: SecretRemoveBody):
        from ..config import SECRET_PATHS
        from ..secret_wipe import remove_secret
        if body.path not in SECRET_PATHS:
            raise HTTPException(404, "chave desconhecida")
        if not body.confirmed:
            raise HTTPException(409, {"code": "confirm_required"})
        report = remove_secret(ctrl.settings, body.path)
        ctrl.settings_changed(paths=[body.path])
        broadcast_settings()
        hub.publish({"type": "engines", "data": ctrl.translation_engines()})
        from ..secret_wipe import env_status
        report["env"] = env_status() if body.path == "ai.gemini_key" else []
        return report

    @api.get("/secrets/env")
    def secret_env():
        from ..secret_wipe import env_status
        return {"vars": env_status(), "platform": sys.platform}

    @api.post("/secrets/env/remove")
    def secret_env_remove(body: EnvRemoveBody):
        from ..secret_wipe import ENV_NAMES, remove_user_env
        if body.name not in ENV_NAMES:
            raise HTTPException(404, "variável desconhecida")
        if not body.confirmed:
            raise HTTPException(409, {"code": "confirm_required"})
        res = remove_user_env(body.name)
        ctrl.settings_changed(paths=["ai.gemini_key"])
        broadcast_settings()
        return res

    # ---------------------------------------------------------------- histórico
    @api.get("/history")
    def history(limit: int = Query(default=200, ge=1, le=5000)):
        return {"items": ctrl.history.recent(limit), "count": ctrl.history.count()}

    @api.delete("/history")
    def history_clear():
        ctrl.history.clear()
        hub.publish({"type": "history_cleared"})
        return {"ok": True}

    @api.get("/history/export")
    def history_export(fmt: str = Query(default="txt", pattern="^(txt|csv|json)$")):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / f"historico.{fmt}"
            n = ctrl.history.export(p, fmt)
            content = p.read_text(encoding="utf-8-sig" if fmt == "csv" else "utf-8")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return {"filename": f"egt-historico-{stamp}.{fmt}", "content": content, "count": n}

    # ---------------------------------------------------------------- sobre / logs
    @api.get("/logs")
    def logs(n: int = Query(default=200, ge=1, le=2000)):
        return {"path": str(paths.log_file()), "text": logsetup.tail_log(n)}

    @api.get("/about")
    def about():
        mods = {}
        for mod, label in (("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("PIL", "pillow"), ("numpy", "numpy"),
                           ("pytesseract", "pytesseract"), 
                           ("mss", "mss"), ("langdetect", "langdetect"), ("requests", "requests"),
                           ("rapidocr_onnxruntime", "rapidocr-onnxruntime"), ("easyocr", "easyocr"),
                           ("argostranslate", "argostranslate"), ("gtts", "gTTS"),
                           ("speech_recognition", "SpeechRecognition"), ("cv2", "opencv")):
            try:
                if importlib.util.find_spec(mod) is None:
                    mods[label] = None
                    continue
                m = importlib.import_module(mod) if mod in ("fastapi", "uvicorn", "PIL", "numpy", "mss", "requests") \
                    else None
                mods[label] = (getattr(m, "__version__", "") or "ok") if m else "ok"
            except Exception:
                mods[label] = None
        return {"app": APP_NAME, "version": __version__, "author": APP_AUTHOR,
                "python": platform.python_version(), "platform": f"{platform.system()} {platform.release()}",
                "config_dir": str(paths.config_dir()), "logs_dir": str(paths.logs_dir()),
                "log_file": str(paths.log_file()), "modules": mods}

    # ---------------------------------------------------------------- componentes (ajuda opcional de instalação)
    from ..components.base import ComponentError

    def comps():
        svc = ctrl.components()
        svc.emit = hub.publish
        svc.dm.emit = hub.publish
        return svc

    def comp_call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except KeyError:
            raise HTTPException(404, "componente desconhecido")
        except ComponentError as exc:
            raise HTTPException(409, {"code": exc.code, "message": str(exc)})
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @api.get("/components")
    def components_list():
        return comps().list_view()

    @api.get("/components/paths")
    def components_paths():
        return comps().paths()

    @api.post("/components/check")
    def components_check_all():
        return comps().check_all()

    @api.post("/components/rescan")
    def components_rescan_all():
        return comp_call(comps().rescan, "")

    @api.get("/components/jobs")
    def components_jobs():
        return comps().dm.list()

    @api.post("/components/jobs/{job_id}/cancel")
    def components_job_cancel(job_id: str):
        return {"ok": comps().cancel(job_id)}

    @api.post("/components/run-installer")
    def components_run_installer(body: CompPathBody):
        return comp_call(comps().run_installer, body.path, body.confirmed)

    @api.post("/components/location")
    def components_location(body: CompLocationBody):
        res = comp_call(comps().set_location, body.id, body.path, body.copy_existing, body.reset)
        return res

    @api.post("/components/validate-dir")
    def components_validate(body: CompPathBody):
        from ..components.store import validate_dir
        return validate_dir(body.path)

    @api.post("/components/_demo")
    def components_demo(body: CompDemoBody):
        d = getattr(comps(), "demo", None)
        if d is None or not getattr(d, "active", False):
            raise HTTPException(404, "disponível só no modo demonstração")
        if body.offline is not None:
            d.offline = body.offline
        if body.python is not None:
            d.python = body.python
            comps().ctx.clear_cache()
        if body.ollama is not None:
            d.ollama_up = body.ollama
        return {"offline": d.offline, "python": d.python, "ollama": d.ollama_up, "opened": d.opened}

    @api.post("/components/{cid}/check")
    def components_check(cid: str, body: CompItemBody = Body(default=CompItemBody())):
        return comp_call(comps().check, cid, body.item)

    @api.post("/components/{cid}/install")
    def components_install(cid: str, body: CompItemBody):
        return comp_call(comps().install, cid, body.item, body.confirmed)

    @api.post("/components/{cid}/remove")
    def components_remove(cid: str, body: CompItemBody):
        return comp_call(comps().remove, cid, body.item, body.confirmed)

    @api.post("/components/{cid}/rescan")
    def components_rescan(cid: str):
        return comp_call(comps().rescan, cid)

    @api.post("/components/{cid}/folder")
    def components_folder(cid: str):
        return {"path": comp_call(comps().folder_for, cid)}

    app.include_router(api)

    # ---------------------------------------------------------------- WebSocket
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        origin = ws.headers.get("origin")
        import re
        sent = ws.query_params.get("token", "")
        ok = (host_ok(ws.headers.get("host", "")) and secrets.compare_digest(sent.encode(), token.encode())
              and (origin is None or re.match(ALLOWED_ORIGIN_RE, origin)))
        if not ok:
            await ws.close(code=4401)
            return
        await ws.accept()
        q = hub.add_client()
        try:
            await ws.send_text(json.dumps({"type": "hello", "data": ctrl.snapshot()}, ensure_ascii=False,
                                          default=str))

            async def reader():
                while True:
                    msg = await ws.receive_text()
                    if msg == "ping":
                        await ws.send_text('{"type":"pong"}')

            rtask = asyncio.create_task(reader())
            try:
                while True:
                    get = asyncio.create_task(q.get())
                    done, _ = await asyncio.wait({get, rtask}, return_when=asyncio.FIRST_COMPLETED)
                    if rtask in done:
                        get.cancel()
                        break
                    await ws.send_text(get.result())
            finally:
                rtask.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.remove_client(q)

    return app
