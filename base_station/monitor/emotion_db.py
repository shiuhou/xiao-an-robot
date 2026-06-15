"""SQLite interface for emotion data.

This MVP uses only Python's standard sqlite3 module and initializes tables from
agent/data/schema.sql so the base station and Agent share one schema source.

OpenFace engine fields (fatigue_level / observation_quality / evidence_codes /
algorithm_version / presence_state / valence / au_json) are added via runtime
ALTER migrations (same pattern as the legacy ``polarity`` column) so the new
perception contract flows through without editing schema.sql or breaking old DBs.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any


# Severity ranking for summarizing the most severe recent fatigue level.
_LEVEL_SEVERITY = {"insufficient_evidence": 0, "low": 1, "medium": 2, "high": 3}

# Columns added on top of the legacy emotions table, in insert order.
_NEW_COLUMNS = (
    ("fatigue_level", "ALTER TABLE emotions ADD COLUMN fatigue_level TEXT"),
    ("observation_quality", "ALTER TABLE emotions ADD COLUMN observation_quality REAL"),
    ("evidence_codes", "ALTER TABLE emotions ADD COLUMN evidence_codes TEXT"),
    ("algorithm_version", "ALTER TABLE emotions ADD COLUMN algorithm_version TEXT"),
    ("presence_state", "ALTER TABLE emotions ADD COLUMN presence_state TEXT"),
    ("valence", "ALTER TABLE emotions ADD COLUMN valence TEXT"),
    ("au_json", "ALTER TABLE emotions ADD COLUMN au_json TEXT"),
)


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
            self._migrate_schema()

    def _migrate_schema(self) -> None:
        emotion_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(emotions)").fetchall()
        }
        if "polarity" not in emotion_columns:
            self.conn.execute("ALTER TABLE emotions ADD COLUMN polarity TEXT DEFAULT '正面'")
        for column, ddl in _NEW_COLUMNS:
            if column not in emotion_columns:
                self.conn.execute(ddl)

    @staticmethod
    def _to_json_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        polarity: str = "正面",
        timestamp: int | None = None,
        *,
        fatigue_level: str | None = None,
        observation_quality: float | None = None,
        evidence_codes: Any = None,
        algorithm_version: str | None = None,
        presence_state: str | None = None,
        valence: str | None = None,
        au_json: Any = None,
    ) -> int:
        timestamp = int(time.time() * 1000) if timestamp is None else timestamp
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO emotions (
                    timestamp, source, emotion_tag, confidence, fatigue_score, polarity,
                    fatigue_level, observation_quality, evidence_codes, algorithm_version,
                    presence_state, valence, au_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp, source, emotion_tag, confidence, fatigue_score, polarity,
                    fatigue_level, observation_quality, self._to_json_text(evidence_codes),
                    algorithm_version, presence_state, valence, self._to_json_text(au_json),
                ),
            )
        return int(cursor.lastrowid)

    def query_recent(self, seconds: int = 300, now_ms: int | None = None) -> list[dict[str, Any]]:
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        since_ms = now_ms - int(seconds * 1000)
        cursor = self.conn.execute(
            """
            SELECT id, timestamp, source, emotion_tag, confidence, fatigue_score, polarity,
                   fatigue_level, observation_quality, evidence_codes, algorithm_version,
                   presence_state, valence, au_json
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
                "fatigue_level_top": None,
                "fatigue_levels_count": {},
            }

        emotion_counts = Counter(row["emotion_tag"] for row in rows)
        # fatigue_score may be NULL (insufficient_evidence) -> exclude from the average.
        fatigue_scores = [float(row["fatigue_score"]) for row in rows if row["fatigue_score"] is not None]
        levels = [row["fatigue_level"] for row in rows if row["fatigue_level"]]
        fatigue_level_top = (
            max(levels, key=lambda lvl: _LEVEL_SEVERITY.get(lvl, -1)) if levels else None
        )
        return {
            "count": len(rows),
            "avg_fatigue_score": (sum(fatigue_scores) / len(fatigue_scores)) if fatigue_scores else 0.0,
            "max_confidence": max(float(row["confidence"]) for row in rows),
            "top_emotion": emotion_counts.most_common(1)[0][0],
            "emotions_count": dict(emotion_counts),
            "fatigue_level_top": fatigue_level_top,
            "fatigue_levels_count": dict(Counter(levels)),
        }
