"""Tipos comuns do gerenciador de componentes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .download import Expect, Job
from .net import Http
from .store import ComponentsStore
from . import sysinfo


class ComponentError(Exception):
    """Pedido impossível: `code` é um motivo curto (a UI traduz para linguagem simples)."""

    def __init__(self, code: str, msg: str = ""):
        super().__init__(msg or code)
        self.code = code


@dataclass
class Detect:
    installed: bool = False
    version: str = ""
    location: str = ""
    builtin: bool = False            # veio junto com o programa
    in_user_dir: bool = False        # está na pasta de componentes (pode ser removido pelo app)
    detail: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Avail:
    ok: bool = False
    latest: str = ""
    size: Optional[int] = None
    url: str = ""
    filename: str = ""
    expect: Expect = field(default_factory=Expect)
    error: str = ""                  # código: 'offline' | 'rate_limit' | 'unavailable' | texto curto
    offline: bool = False
    items: dict[str, dict] = field(default_factory=dict)
    note: str = ""                   # código extra: 'heavy' | 'no_installer' ...


@dataclass
class Plan:
    label: str
    url: str = ""
    filename: str = ""
    expect: Expect = field(default_factory=Expect)
    dest_dir: Optional[Path] = None
    post: Optional[Callable[[Job], None]] = None
    task: Optional[Callable[[Job], None]] = None
    is_installer: bool = False       # arquivo é um instalador (o usuário confirma para executar)


@dataclass
class Ctx:
    store: ComponentsStore
    http: Http
    get_setting: Callable[[str, Any], Any]
    usage: Callable[[], dict]
    run: Callable[..., tuple] = sysinfo.run_cmd
    stream: Callable[..., int] = sysinfo.run_streaming
    frozen: bool = sysinfo.FROZEN
    plat: str = sysinfo.sys.platform
    _pythons: Optional[Callable[[], list]] = None
    demo: Any = None
    _cache: dict = field(default_factory=dict)

    def pythons(self, refresh: bool = False) -> list:
        if self._pythons is not None:
            return self._pythons()
        if refresh or "py" not in self._cache:
            self._cache["py"] = sysinfo.find_system_pythons()
        return self._cache["py"]

    def clear_cache(self) -> None:
        self._cache.clear()


def ver_tuple(v: str) -> tuple:
    parts = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in parts[:5])


def is_newer(latest: str, current: str) -> bool:
    a, b = ver_tuple(latest), ver_tuple(current)
    return bool(a) and bool(b) and a > b


class Component:
    id: str = ""
    category: str = "runtime"
    frozen_ok: bool = True                     # dá para carregar o que for instalado, dentro do app empacotado?
    heavy: bool = False

    # -- detecção local (rápida)
    def detect(self, ctx: Ctx) -> Detect:
        raise NotImplementedError

    def folder(self, ctx: Ctx) -> Optional[Path]:
        try:
            return ctx.store.dir_for(self.id)
        except KeyError:
            return None

    def items(self, ctx: Ctx, det: Detect, av: Optional[Avail]) -> list[dict]:
        return []

    def needed(self, ctx: Ctx, det: Detect) -> bool:
        return False

    def offer(self, ctx: Ctx, det: Detect) -> bool:
        """Mesmo já funcionando, existe algo opcional para instalar (ex.: Python do computador)?"""
        return False

    def blocker(self, ctx: Ctx, item: str = "") -> str:
        return ""

    # -- rede (somente fontes oficiais)
    def check(self, ctx: Ctx) -> Avail:
        return Avail(ok=False, error="unavailable")

    def check_item(self, ctx: Ctx, item: str) -> dict:
        return {}

    # -- instalar / remover
    def plan(self, ctx: Ctx, item: str, av: Avail) -> Plan:
        raise ComponentError("no_install")

    def removable(self, ctx: Ctx, det: Detect, item: str = "") -> bool:
        return False

    def remove(self, ctx: Ctx, item: str = "") -> dict:
        raise ComponentError("no_remove")

    def rescan(self, ctx: Ctx) -> dict:
        return {}

    def manual(self, ctx: Ctx) -> dict:
        return {"links": [], "commands": [], "notes": []}

    def add_files(self, ctx: Ctx) -> Optional[dict]:
        """Onde colocar arquivos manualmente: {'key': i18n, 'exts': [...]}."""
        return None
