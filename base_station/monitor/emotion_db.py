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
    def __init__(
        self,
        db_path: str,
        memory_store: Any | None = None,
        mirror_to_memory: bool = False,
    ):
        self.db_path = db_path
        self.memory_store = memory_store
        self.mirror_to_memory = mirror_to_memory
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
            self._migrate_schema()

    def _migrate_schema(self) -> None:
        emotion_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(emotions)").fetchall()
        }
        if "polarity" not in emotion_columns:
            self.conn.execute("ALTER TABLE emotions ADD COLUMN polarity TEXT DEFAULT '正面'")

    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        polarity: str = "正面",
        timestamp: int | None = None,
    ) -> int:
        event_timestamp_ms = timestamp
        timestamp = int(time.time() * 1000) if timestamp is None else timestamp
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO emotions (timestamp, source, emotion_tag, confidence, fatigue_score, polarity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (timestamp, source, emotion_tag, confidence, fatigue_score, polarity),
            )
        row_id = int(cursor.lastrowid)
        self._mirror_emotion_event(
            row_id=row_id,
            source=source,
            emotion_tag=emotion_tag,
            confidence=confidence,
            fatigue_score=fatigue_score,
            polarity=polarity,
            timestamp=timestamp,
            event_timestamp_ms=event_timestamp_ms,
        )
        return row_id

    def _mirror_emotion_event(
        self,
        row_id: int,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float,
        polarity: str,
        timestamp: int | None,
        event_timestamp_ms: int | None,
    ) -> None:
        if not self.mirror_to_memory or self.memory_store is None:
            return

        insert_event = getattr(self.memory_store, "insert_event", None)
        if insert_event is None:
            return

        payload = {
            "timestamp_ms": timestamp,
            "source": source,
            "emotion_tag": emotion_tag,
            "confidence": confidence,
            "fatigue_score": fatigue_score,
            "polarity": polarity,
            "emotion_row_id": row_id,
            "emotion_id": row_id,
        }
        text = (
            f"emotion={emotion_tag} "
            f"fatigue_score={fatigue_score} "
            f"confidence={confidence}"
        )

        try:
            insert_event(
                event_type="emotion.sample",
                source=source or "emotion_db",
                text=text,
                payload=dict(payload),
                timestamp_ms=event_timestamp_ms,
                privacy_level="normal",
            )
        except Exception:
            return

    def query_recent(self, seconds: int = 300, now_ms: int | None = None) -> list[dict[str, Any]]:
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        since_ms = now_ms - int(seconds * 1000)
        cursor = self.conn.execute(
            """
            SELECT id, timestamp, source, emotion_tag, confidence, fatigue_score, polarity
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
