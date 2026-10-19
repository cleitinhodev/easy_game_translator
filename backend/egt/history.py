"""Histórico de traduções (SQLite) + exportação TXT/CSV/JSON."""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Optional

from .db import Database

KEEP_LAST = 5000


class HistoryStore:
    def __init__(self, db: Database):
        self.db = db
        self._n = 0

    def add(self, original: str, translated: str, *, channel: str = "uni", src: str = "", tgt: str = "",
            engine: str = "", from_cache: bool = False, profile: str = "") -> dict:
        self.db.execute(
            "INSERT INTO history(ts,channel,original,translated,src,tgt,engine,from_cache,profile) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (time.time(), channel, original, translated, src, tgt, engine, int(from_cache), profile))
        self._n += 1
        if self._n % 100 == 0:
            self.db.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT ?)",
                            (KEEP_LAST,))
        rows = self.db.execute("SELECT * FROM history ORDER BY id DESC LIMIT 1")
        return dict(rows[0]) if rows else {}

    def recent(self, limit: int = 200) -> list[dict]:
        rows = self.db.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) AS n FROM history")[0]["n"])

    def clear(self) -> None:
        self.db.execute("DELETE FROM history")

    def export(self, path: Path | str, fmt: Optional[str] = None, limit: int = KEEP_LAST) -> int:
        """Exporta (mais antigo primeiro). fmt: 'txt' | 'csv' | 'json' (padrão: extensão)."""
        path = Path(path)
        fmt = (fmt or path.suffix.lstrip(".") or "txt").lower()
        rows = list(reversed(self.recent(limit)))
        if fmt == "json":
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        elif fmt == "csv":
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["id", "data_hora", "canal", "original", "traducao", "origem", "destino", "motor", "cache"])
                for r in rows:
                    w.writerow([r["id"], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])), r["channel"],
                                r["original"], r["translated"], r["src"], r["tgt"], r["engine"], r["from_cache"]])
        else:
            with path.open("w", encoding="utf-8") as f:
                for r in rows:
                    ts = time.strftime("%H:%M:%S", time.localtime(r["ts"]))
                    f.write(f"[{ts}] {r['original']}\n    → {r['translated']}\n\n")
        return len(rows)
