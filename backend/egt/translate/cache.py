"""Cache persistente de traduções em SQLite: (texto normalizado, origem, destino, motor)."""
from __future__ import annotations

import threading
import time
from typing import Optional

from ..change import normalize_text
from ..db import Database

MAX_ROWS = 50_000


class TranslationCache:
    def __init__(self, db: Database, max_rows: int = MAX_ROWS):
        self.db = db
        self.max_rows = max_rows
        self._lock = threading.Lock()
        self._puts = 0

    @staticmethod
    def key(text: str) -> str:
        return normalize_text(text)

    def get(self, text: str, src: str, tgt: str, engine: str) -> Optional[str]:
        k = self.key(text)
        rows = self.db.execute(
            "SELECT result FROM translations WHERE text_norm=? AND src=? AND tgt=? AND engine=?",
            (k, src, tgt, engine))
        if not rows:
            return None
        self.db.execute(
            "UPDATE translations SET hits=hits+1, last_used=? "
            "WHERE text_norm=? AND src=? AND tgt=? AND engine=?", (time.time(), k, src, tgt, engine))
        return rows[0]["result"]

    def put(self, text: str, src: str, tgt: str, engine: str, result: str) -> None:
        if not result or not text.strip():
            return
        now = time.time()
        self.db.execute(
            "INSERT INTO translations(text_norm,src,tgt,engine,result,created,last_used,hits) "
            "VALUES(?,?,?,?,?,?,?,0) "
            "ON CONFLICT(text_norm,src,tgt,engine) DO UPDATE SET result=excluded.result, last_used=excluded.last_used",
            (self.key(text), src, tgt, engine, result, now, now))
        with self._lock:
            self._puts += 1
            prune = self._puts % 200 == 0
        if prune:
            self.prune()

    def prune(self) -> None:
        n = self.count()
        if n > self.max_rows:
            self.db.execute(
                "DELETE FROM translations WHERE rowid IN (SELECT rowid FROM translations "
                "ORDER BY last_used ASC LIMIT ?)", (n - self.max_rows,))

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) AS n FROM translations")[0]["n"])

    def stats(self) -> dict:
        rows = self.db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(hits),0) AS hits FROM translations")[0]
        by_engine = {r["engine"]: r["n"] for r in self.db.execute(
            "SELECT engine, COUNT(*) AS n FROM translations GROUP BY engine")}
        return {"entries": int(rows["n"]), "hits": int(rows["hits"]), "by_engine": by_engine}

    def clear(self) -> None:
        self.db.execute("DELETE FROM translations")
