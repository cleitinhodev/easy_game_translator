"""Modo demonstração (EGT_DEMO=1): captura sintética + tradutor offline falso.

Serve para testes de interface/screenshots sem jogo, sem rede e sem Tesseract: o OCR real (RapidOCR)
lê legendas desenhadas numa imagem gerada, e o tradutor devolve frases em português de uma tabela.
Não é usado em produção.
"""
from __future__ import annotations

import os
import time
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

from .capture.screen import ScreenGrabber, normalize_bbox
from .translate.base import Translator

LINES = [
    ("The king awaits you in the throne room.", "O rei espera por você na sala do trono."),
    ("Take this key. It opens the old cellar door.", "Pegue esta chave. Ela abre a porta da velha adega."),
    ("We must leave before the storm arrives.", "Precisamos partir antes que a tempestade chegue."),
    ("Careful! The bridge will not hold much longer.", "Cuidado! A ponte não vai aguentar por muito mais tempo."),
    ("You have found the legendary sword of dawn.", "Você encontrou a lendária espada da aurora."),
]
CHAT = [
    ("Player42: Anyone want to join the raid tonight?", "Player42: Alguém quer entrar na raid hoje à noite?"),
    ("Mira: I will bring the healing potions.", "Mira: Eu levo as poções de cura."),
    ("Dax: Meet at the north gate in ten minutes.", "Dax: Encontro no portão norte em dez minutos."),
]
_TABLE = {a.lower(): b for a, b in LINES + CHAT}


def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


class DemoGrabber(ScreenGrabber):
    def __init__(self, period: float = 7.0):
        super().__init__(prefer_mss=False)
        self.period = period
        self._chan: dict[tuple, int] = {}
        self.backend = "demo"

    def grab(self, bbox: Sequence[float]) -> Image.Image:
        box = normalize_bbox(bbox)
        if box is None:
            raise ValueError("região inválida")
        w, h = box[2] - box[0], box[3] - box[1]
        idx = self._chan.setdefault(box, len(self._chan))
        pool = CHAT if idx % 2 else LINES
        text = pool[(int(time.time() / self.period) + idx) % len(pool)][0]
        img = Image.new("RGB", (w, h), (18, 18, 24))
        d = ImageDraw.Draw(img)
        size = max(14, min(int(h * 0.5), 34))
        f = _font(size)
        while d.textlength(text, font=f) > w - 16 and size > 11:
            size -= 1
            f = _font(size)
        d.text((8, (h - size) // 2 - 2), text, font=f, fill=(245, 245, 245))
        return img


class DemoEngine(Translator):
    id, name, online = "google", "Demo (offline)", False

    def available(self):
        return True, ""

    def translate(self, text: str, src: str, tgt: str) -> str:
        time.sleep(0.12)
        key = " ".join(text.lower().split())
        for k, v in _TABLE.items():
            if k.strip(".! ") in key or key.strip(".! ") in k:
                return v
        import difflib        # OCR pode errar uma letra: aceita quase-igual (só no modo demo)
        best = max(_TABLE, key=lambda k: difflib.SequenceMatcher(None, k.strip(".! "), key.strip(".! ")).ratio())
        if difflib.SequenceMatcher(None, best.strip(".! "), key.strip(".! ")).ratio() >= 0.8:
            return _TABLE[best]
        return "[demo] " + text


def install(ctrl) -> None:
    ctrl.grabber = DemoGrabber(period=float(os.environ.get("EGT_DEMO_PERIOD", "7")))
    ctrl.pipeline.capture_fn = ctrl.grabber.grab
    eng = DemoEngine()
    from .translate.manager import ai_engine

    def engines():                                  # a IA selecionada (só ela) continua valendo na demonstração
        ai = ai_engine(ctrl.settings, ctrl.settings.get("ai.mode", "off"))
        return ([ai] if ai is not None else []) + [eng]
    ctrl.manager._engines = engines
    ctrl.check_network = lambda force=False: setattr(ctrl, "net", "online") or "online"  # type: ignore[method-assign]
    ctrl.net = "online"
    try:                                        # gerenciador de componentes com fontes "oficiais" fictícias
        from .components.demo import DemoSource
        from .components.service import ComponentService
        from .components.store import get_store
        d = DemoSource()
        svc = ComponentService(get_store(), get_setting=ctrl.settings.get, usage=ctrl.components_usage,
                               on_changed=ctrl._components_changed, demo=d, pythons=d.pythons,
                               stream=d.stream, startfile=d.startfile)
        svc.ctx.plat = os.environ.get("EGT_DEMO_PLATFORM", "win32")
        svc.ctx.frozen = os.environ.get("EGT_DEMO_FROZEN", "0") == "1"
        ctrl._components = svc
    except Exception:  # noqa: BLE001
        pass
