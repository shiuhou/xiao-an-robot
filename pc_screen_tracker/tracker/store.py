"""SQLite persistence for raw activity samples.

We store one row per sampling tick (default every 5s). Sessions/statistics are
derived at report time, which keeps the write path trivial and crash-safe.

The optional `frames` table (only written when the understanding layer is on)
persists the richer FrameRecord stream — window + captured body text — that the
segmenter/understander consume live. It sits next to `samples` in the same db;
`samples` stays the stats source, `frames` is the understanding source.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import fields
from pathlib import Path
from typing import Any

from tracker.frames import FrameRecord

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

CREATE TABLE IF NOT EXISTS frames (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms          INTEGER NOT NULL,
    frame          INTEGER,
    hwnd           INTEGER,
    app            TEXT,
    title          TEXT,
    kind           TEXT,
    capture_policy TEXT,
    url            TEXT,
    headline       TEXT,
    content        TEXT,           -- JSON list[str]; body text stays on the PC
    mode           TEXT,
    keys           INTEGER,
    clicks         INTEGER,
    scrolls        INTEGER,
    mouse_px       REAL,
    dwell_s        REAL,
    idle_s         REAL,
    uia_nodes      INTEGER,
    uia_docs       INTEGER,
    elapsed_ms     INTEGER,
    truncated      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_frames_ts ON frames (ts_ms);
"""

# FrameRecord fields whose value is stored verbatim (content is handled apart).
_FRAME_COLS = [f.name for f in fields(FrameRecord) if f.name != "content"]


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

    def insert_frame(self, rec: FrameRecord) -> None:
        cols = _FRAME_COLS + ["content"]
        values = [getattr(rec, c) for c in _FRAME_COLS]
        values.append(json.dumps(rec.content, ensure_ascii=False))
        with self._lock:
            self._conn.execute(
                f"INSERT INTO frames ({','.join(cols)}) "
                f"VALUES ({','.join('?' for _ in cols)})",
                values,
            )
            self._conn.commit()

    def query_frames(self, since_ms: int, until_ms: int | None = None) -> list[FrameRecord]:
        until_ms = until_ms if until_ms is not None else int(time.time() * 1000)
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM frames WHERE ts_ms >= ? AND ts_ms <= ? ORDER BY ts_ms",
                (since_ms, until_ms),
            )
            rows = cur.fetchall()
        out: list[FrameRecord] = []
        for row in rows:
            kwargs = {c: row[c] for c in _FRAME_COLS}
            try:
                kwargs["content"] = json.loads(row["content"]) if row["content"] else []
            except (TypeError, ValueError):
                kwargs["content"] = []
            kwargs["truncated"] = bool(kwargs.get("truncated"))
            out.append(FrameRecord(**kwargs))
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
