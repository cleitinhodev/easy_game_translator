"""Interface dos motores de tradução. / Translator backend interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class TranslationError(Exception):
    """Falha ao traduzir (rede, resposta inválida...)."""


class RateLimited(TranslationError):
    """Limite de requisições atingido; `retry_after` em segundos (opcional)."""

    def __init__(self, msg: str = "limite de requisições", retry_after: Optional[float] = None):
        super().__init__(msg)
        self.retry_after = retry_after


@dataclass
class TranslationResult:
    text: str
    engine: str = ""
    cached: bool = False
    ok: bool = True
    error: str = ""
    src: str = ""
    tgt: str = ""
    elapsed_ms: float = 0.0
    attempts: list = field(default_factory=list)   # [(engine, "ok"/erro)]


class Translator(ABC):
    id: str = ""
    name: str = ""
    online: bool = True
    optional_dep: str = ""     # dica de instalação

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """(pronto para uso?, motivo). Nunca levanta exceção."""

    @abstractmethod
    def translate(self, text: str, src: str, tgt: str) -> str:
        """Traduz `text`. `src` pode ser '' (auto). Levanta TranslationError/RateLimited."""


def split_chunks(text: str, limit: int) -> list[str]:
    """Divide o texto em pedaços <= limit respeitando linhas/frases."""
    if len(text) <= limit:
        return [text]
    import re
    parts = re.split(r"(?<=[\n.!?。！？])\s*", text)
    chunks, cur = [], ""
    for p in parts:
        if not p:
            continue
        while len(p) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:limit])
            p = p[limit:]
        if len(cur) + len(p) + 1 > limit and cur:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip() if cur else p
    if cur:
        chunks.append(cur)
    return chunks
