"""Banco SQLite compartilhado (cache de tradução + histórico). Thread-safe via lock.

Shared SQLite database (translation cache + history).
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    text_norm TEXT NOT NULL,
    src TEXT NOT NULL,
    tgt TEXT NOT NULL,
    engine TEXT NOT NULL,
    result TEXT NOT NULL,
    created REAL NOT NULL,
    last_used REAL NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (text_norm, src, tgt, engine)
);
CREATE INDEX IF NOT EXISTS idx_tr_last_used ON translations(last_used);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    channel TEXT NOT NULL DEFAULT 'uni',
    original TEXT NOT NULL,
    translated TEXT NOT NULL,
    src TEXT NOT NULL DEFAULT '',
    tgt TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL DEFAULT '',
    from_cache INTEGER NOT NULL DEFAULT 0,
    profile TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_hist_ts ON history(ts);
"""


class Database:
    """Uma conexão única protegida por lock (uso leve, várias threads)."""

    def __init__(self, path: Optional[Path | str] = None):
        self.path = str(path) if path is not None else ":memory:"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            if self.path != ":memory:":
                try:
                    self._conn.execute("PRAGMA journal_mode=WAL")
                except sqlite3.DatabaseError:  # pragma: no cover
                    pass
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def execute(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            rows = cur.fetchall()
            self._conn.commit()
            return rows

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:  # pragma: no cover
                pass
