"""SQLite interface for emotion data.

This MVP uses only Python's standard sqlite3 module and initializes tables from
agent/data/schema.sql so the base station and Agent share one schema source.
"""

from __future__ import annotations

import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any


class EmotionDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EmotionDB":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _schema_path(self) -> Path:
        repo_root = Path(__file__).resolve().parents[2]
        return repo_root / "agent" / "data" / "schema.sql"

    def _init_schema(self) -> None:
        schema_path = self._schema_path()
        try:
            schema_sql = schema_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to read database schema at {schema_path}") from exc

        with self.conn:
            self.conn.executescript(schema_sql)

    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        timestamp: int | None = None,
    ) -> int:
        timestamp = int(time.time() * 1000) if timestamp is None else timestamp
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO emotions (timestamp, source, emotion_tag, confidence, fatigue_score)
                VALUES (?, ?, ?, ?, ?)
                """,
                (timestamp, source, emotion_tag, confidence, fatigue_score),
            )
        return int(cursor.lastrowid)

    def query_recent(self, seconds: int = 300, now_ms: int | None = None) -> list[dict[str, Any]]:
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        since_ms = now_ms - int(seconds * 1000)
        cursor = self.conn.execute(
            """
            SELECT id, timestamp, source, emotion_tag, confidence, fatigue_score
            FROM emotions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp DESC
            """,
            (since_ms, now_ms),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_recent_summary(self, seconds: int = 300, now_ms: int | None = None) -> dict[str, Any]:
        rows = self.query_recent(seconds=seconds, now_ms=now_ms)
        if not rows:
            return {
                "count": 0,
                "avg_fatigue_score": 0.0,
                "max_confidence": 0.0,
                "top_emotion": None,
                "emotions_count": {},
            }

        emotion_counts = Counter(row["emotion_tag"] for row in rows)
        return {
            "count": len(rows),
            "avg_fatigue_score": sum(float(row["fatigue_score"]) for row in rows) / len(rows),
            "max_confidence": max(float(row["confidence"]) for row in rows),
            "top_emotion": emotion_counts.most_common(1)[0][0],
            "emotions_count": dict(emotion_counts),
        }
