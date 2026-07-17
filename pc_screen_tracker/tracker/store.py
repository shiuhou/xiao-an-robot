"""SQLite persistence for raw activity samples.

We store one row per sampling tick (default every 5s). Sessions/statistics are
derived at report time, which keeps the write path trivial and crash-safe.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms       INTEGER NOT NULL,
    app         TEXT,
    title       TEXT,
    category    TEXT,
    domain      TEXT,
    url         TEXT,
    idle_sec    REAL,
    active      INTEGER,          -- 1 if user was active during the interval
    keys        INTEGER,          -- keystrokes counted in the interval
    clicks      INTEGER,          -- mouse clicks in the interval
    scrolls     INTEGER,          -- scroll events in the interval
    mouse_px    REAL,             -- mouse travel (pixels) in the interval
    interval_s  REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples (ts_ms);
CREATE INDEX IF NOT EXISTS idx_samples_app ON samples (app);
CREATE INDEX IF NOT EXISTS idx_samples_cat ON samples (category);
"""


class Store:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def insert_sample(self, row: dict[str, Any]) -> None:
        cols = ("ts_ms", "app", "title", "category", "domain", "url",
                "idle_sec", "active", "keys", "clicks", "scrolls",
                "mouse_px", "interval_s")
        with self._lock:
            self._conn.execute(
                f"INSERT INTO samples ({','.join(cols)}) "
                f"VALUES ({','.join('?' for _ in cols)})",
                [row.get(c) for c in cols],
            )
            self._conn.commit()

    def query(self, since_ms: int, until_ms: int | None = None) -> list[sqlite3.Row]:
        until_ms = until_ms if until_ms is not None else int(time.time() * 1000)
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM samples WHERE ts_ms >= ? AND ts_ms <= ? ORDER BY ts_ms",
                (since_ms, until_ms),
            )
            return cur.fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
