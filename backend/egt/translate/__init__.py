"""Tradução: cache SQLite + motores plugáveis (online, offline e IA opcional)."""
from .base import RateLimited, TranslationError, TranslationResult, Translator
from .cache import TranslationCache
from .manager import TranslationManager, build_engines

__all__ = ["RateLimited", "TranslationError", "TranslationResult", "Translator",
           "TranslationCache", "TranslationManager", "build_engines"]
