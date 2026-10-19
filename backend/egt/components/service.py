"""Serviço do gerenciador de componentes: junta registro + detecção + verificação + download + remoção."""
from __future__ import annotations

import concurrent.futures as cf
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import defs
from .base import Avail, Component, ComponentError, Ctx, Detect, is_newer
from .download import DownloadManager, Job
from .net import AllowList, Http
from .store import ComponentsStore, validate_dir

log = logging.getLogger(__name__)

INSTALLER_EXT = (".exe", ".msi")


class ComponentService:
    def __init__(self, store: ComponentsStore, http: Optional[Http] = None, get_setting: Optional[Callable] = None,
                 usage: Optional[Callable[[], dict]] = None, emit: Optional[Callable[[dict], None]] = None,
                 on_changed: Optional[Callable[[str], None]] = None, demo: Any = None, run: Optional[Callable] = None,
                 stream: Optional[Callable] = None, pythons: Optional[Callable] = None, startfile: Optional[Callable] = None):
        self.store = store
        self.emit = emit or (lambda e: None)
        self.on_changed = on_changed
        self.demo = demo
        http = http or (demo.http if demo is not None else Http(AllowList()))
        self.ctx = Ctx(store, http, get_setting or (lambda p, d=None: d), usage or (lambda: {}), demo=demo)
        if run:
            self.ctx.run = run
        if stream:
            self.ctx.stream = stream
        if pythons:
            self.ctx._pythons = pythons
        self.registry: dict[str, Component] = {c.id: c for c in defs.ALL}
        self.avail: dict[str, Avail] = {}
        self.checked_at: dict[str, float] = {}
        self.dm = DownloadManager(self.ctx.http, store.downloads, self._emit, on_done=self._done)
        self._startfile = startfile or getattr(os, "startfile", None)
        self._lock = threading.Lock()

    # ------------------------------------------------------------ util
    def _emit(self, ev: dict) -> None:
        self.emit(ev)

    def comp(self, cid: str) -> Component:
        try:
            return self.registry[cid]
        except KeyError:
            raise KeyError(cid) from None

    def _done(self, job: Job) -> None:
        self.ctx.clear_cache()
        self.emit({"type": "component_changed", "data": {"component": job.component, "item": job.item}})
        if self.on_changed:
            try:
                self.on_changed(job.component)
            except Exception:  # noqa: BLE001
                log.exception("on_changed falhou")

    def _changed(self, cid: str, item: str = "") -> None:
        self.ctx.clear_cache()
        self.emit({"type": "component_changed", "data": {"component": cid, "item": item}})
        if self.on_changed:
            try:
                self.on_changed(cid)
            except Exception:  # noqa: BLE001
                log.exception("on_changed falhou")

    # ------------------------------------------------------------ visão
    def _safe_detect(self, c: Component) -> Detect:
        try:
            return c.detect(self.ctx)
        except Exception as exc:  # noqa: BLE001
            log.warning("detect(%s) falhou: %s", c.id, exc)
            return Detect(False, detail=f"erro: {exc}")

    def view(self, cid: str, det: Optional[Detect] = None) -> dict:
        c = self.comp(cid)
        det = det or self._safe_detect(c)
        av = self.avail.get(cid)
        try:
            items = c.items(self.ctx, det, av)
        except Exception:  # noqa: BLE001
            log.exception("items(%s)", cid)
            items = []
        try:
            needed = bool(c.needed(self.ctx, det)) or any(i.get("needed") for i in items)
            offer = bool(c.offer(self.ctx, det))
            blocker = c.blocker(self.ctx, "")
        except Exception:  # noqa: BLE001
            log.exception("view(%s)", cid)
            needed, offer, blocker = False, False, ""
        missing_items = [i for i in items if i.get("needed") and not i.get("installed")]
        latest = av.latest if av and av.ok else ""
        can_update = det.installed and not det.builtin and bool(latest) and bool(det.version) \
            and is_newer(latest, det.version) and cid not in ("python", "rapidocr") \
            and (not isinstance(c, defs.PipComponent) or det.in_user_dir)
        if det.detail == "not_windows" or (blocker == "not_windows"):
            status = "unavailable"
        elif missing_items:
            status = "missing"
        elif det.installed:
            status = "update" if can_update else "ok"
        else:
            status = "missing"
        primary: dict = {"action": "none"}
        if status == "update" and not blocker:
            primary = {"action": "update"}
        elif status == "missing":
            if cid == "gemini":
                primary = {"action": "goto_ai"}
            elif missing_items and not c.blocker(self.ctx, missing_items[0]["id"]):
                primary = {"action": "install", "item": missing_items[0]["id"]}
            elif not blocker and not missing_items:
                primary = {"action": "install"}
            elif blocker != "not_windows":
                primary = {"action": "howto"}
        elif status == "ok" and offer and not blocker:
            primary = {"action": "install", "optional": True}
        folder = c.folder(self.ctx)
        job = next((j.view() for j in self.dm.jobs.values() if j.component == cid and j.state in ("queued", "running")), None)
        man = c.manual(self.ctx)
        return {
            "id": cid, "category": c.category, "status": status, "installed": det.installed, "builtin": det.builtin,
            "version": det.version, "latest": latest, "location": det.location, "needed": needed, "offer": offer,
            "primary": primary, "blocker": blocker, "heavy": c.heavy,
            "size": av.size if av and av.ok else None, "checked": av is not None,
            "check_error": (av.error if av and not av.ok else ""), "offline": bool(av and av.offline),
            "note": av.note if av else "", "folder": str(folder) if folder else None,
            "folder_custom": cid in self.store.data["dirs"], "items": items,
            "removable": bool(c.removable(self.ctx, det, "")),
            "manual": {"links": [{"label": a, "url": b} for a, b in man["links"]],
                       "commands": [{"label": a, "cmd": b} for a, b in man["commands"]], "notes": man["notes"]},
            "add_files": c.add_files(self.ctx), "job": job, "detect_extra": _public_extra(det.extra),
        }

    def list_view(self) -> dict:
        comps = list(self.registry.values())
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            dets = list(ex.map(self._safe_detect, comps))
        views = [self.view(c.id, d) for c, d in zip(comps, dets)]
        needed = [v["id"] for v in views if v["needed"]]
        return {"components": views, "summary": {"all_ok": not needed, "needed": needed},
                "paths": self.paths(), "demo": bool(self.demo and getattr(self.demo, "active", False)),
                "frozen": self.ctx.frozen, "platform": self.ctx.plat,
                "jobs": self.dm.list()}

    def paths(self) -> dict:
        return {"root": str(self.store.root()), "default_root": str(self.store.default_root()),
                "dirs": {cid: (str(f) if (f := c.folder(self.ctx)) else None) for cid, c in self.registry.items()},
                "downloads": str(self.store.downloads())}

    # ------------------------------------------------------------ verificar
    def _check_one(self, c: Component) -> Avail:
        try:
            av = c.check(self.ctx)
        except Exception as exc:  # noqa: BLE001
            log.warning("check(%s) falhou: %s", c.id, exc)
            av = Avail(ok=False, error="unavailable")
        with self._lock:
            self.avail[c.id] = av
            self.checked_at[c.id] = time.time()
        return av

    def check(self, cid: str, item: str = "") -> dict:
        c = self.comp(cid)
        if item:
            av = self.avail.get(cid) or self._check_one(c)
            info = c.check_item(self.ctx, item)
            if "error" in info:
                return {"item": item, "error": info["error"]}
            av.items.setdefault(item, {}).update(info)
            return {"item": item, **info}
        self._check_one(c)
        return self.view(cid)

    def check_all(self, timeout: float = 30.0) -> dict:
        cs = [c for c in self.registry.values() if c.id != "gemini"]
        ex = cf.ThreadPoolExecutor(max_workers=6)
        futs = [ex.submit(self._check_one, c) for c in cs]
        cf.wait(futs, timeout=timeout)
        ex.shutdown(wait=False, cancel_futures=True)
        return self.list_view()

    # ------------------------------------------------------------ instalar
    def install(self, cid: str, item: str = "", confirmed: bool = False) -> dict:
        if not confirmed:
            raise ComponentError("confirm_required")
        c = self.comp(cid)
        blk = c.blocker(self.ctx, item)
        if blk:
            raise ComponentError(blk)
        av = self.avail.get(cid)
        if av is None or (item and item not in av.items and not av.ok):
            av = self._check_one(c)
        if av.offline:
            raise ComponentError("offline")
        plan = c.plan(self.ctx, item, av)
        need = av.items.get(item, {}).get("size") if item else av.size
        target = plan.dest_dir or self.store.downloads()
        if need:
            v = validate_dir(str(target), need_bytes=int(need * 1.3))
            if not v["ok"]:
                raise ComponentError("no_space" if "espaço" in " ".join(v["errors"]) else "bad_dir", "; ".join(v["errors"]))
        if plan.task is not None:
            job = self.dm.start_task(cid, item, plan.label, plan.task)
        else:
            job = self.dm.start(cid, item, plan.label, plan.url, plan.filename, plan.expect, plan.dest_dir, plan.post)
        job.installer = bool(plan.is_installer)
        return job.view()

    def cancel(self, job_id: str) -> bool:
        return self.dm.cancel(job_id)

    def remove(self, cid: str, item: str = "", confirmed: bool = False) -> dict:
        if not confirmed:
            raise ComponentError("confirm_required")
        c = self.comp(cid)
        det = self._safe_detect(c)
        if not c.removable(self.ctx, det, item):
            raise ComponentError("not_removable")
        res = c.remove(self.ctx, item)
        self._changed(cid, item)
        return res

    def rescan(self, cid: str = "") -> dict:
        self.ctx.clear_cache()
        out = {}
        for c in ([self.comp(cid)] if cid else self.registry.values()):
            try:
                r = c.rescan(self.ctx)
                if r:
                    out[c.id] = r
            except Exception:  # noqa: BLE001
                log.exception("rescan(%s)", c.id)
        from .store import setup_environment
        setup_environment(self.store)
        self._changed(cid or "*")
        return {"rescanned": out, **self.list_view()}

    # ------------------------------------------------------------ instalador baixado (usuário confirma)
    def run_installer(self, path: str, confirmed: bool = False) -> dict:
        if not confirmed:
            raise ComponentError("confirm_required")
        p = Path(path)
        try:
            rp = p.resolve()
            dl = self.store.downloads().resolve()
        except OSError as exc:
            raise ComponentError("bad_path") from exc
        if dl not in rp.parents or rp.suffix.lower() not in INSTALLER_EXT or not rp.is_file():
            raise ComponentError("bad_path", "só instaladores baixados por este programa")
        if self.ctx.plat != "win32" or self._startfile is None:
            raise ComponentError("not_windows")
        self._startfile(str(rp))
        return {"ok": True}

    # ------------------------------------------------------------ locais
    def set_location(self, cid: str, path: str, copy_existing: bool = False, reset: bool = False) -> dict:
        if cid == "root":
            res = self.store.set_root(path, copy_existing) if not reset else self._reset_root()
        else:
            self.comp(cid)
            if reset:
                self.store.reset_dir(cid)
                res = {"ok": True, "errors": [], "warnings": []}
            else:
                res = self.store.set_dir(cid, path, copy_existing)
        if res.get("ok"):
            from .store import setup_environment
            setup_environment(self.store)
            self._changed(cid)
        return res

    def _reset_root(self) -> dict:
        self.store.data["root"] = ""
        self.store.save()
        return {"ok": True, "errors": [], "warnings": []}

    def folder_for(self, cid: str) -> str:
        """Pasta (criada se faltar) para o botão 📁. Valida id e caminho."""
        if cid == "root":
            r = self.store.root()
            r.mkdir(parents=True, exist_ok=True)
            return str(r)
        c = self.comp(cid)
        f = c.folder(self.ctx)
        if f is None:
            raise ComponentError("no_folder")
        if not self.store.is_allowed(f) and cid != "ollama":
            raise ComponentError("bad_path")
        f.mkdir(parents=True, exist_ok=True)
        return str(f)


def _public_extra(extra: dict) -> dict:
    """Só o que a UI precisa (sem caminhos desnecessários)."""
    out = {}
    for k in ("server", "models", "system", "user", "pairs", "frozen", "runtime", "key", "exe"):
        if k in extra:
            out[k] = extra[k]
    return out
