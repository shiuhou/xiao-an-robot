"""Long-term memory and context retrieval for the agent."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class XiaoAnMemoryStore:
    """SQLite-backed unified memory store for Xiao An."""

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or self._default_db_path())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "XiaoAnMemoryStore":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    @classmethod
    def _repo_root(cls) -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _default_db_path(cls) -> Path:
        return cls._repo_root() / "agent" / "data" / "xiao_an.db"

    @classmethod
    def _schema_path(cls) -> Path:
        return cls._repo_root() / "agent" / "data" / "schema.sql"

    def _init_schema(self) -> None:
        schema_path = self._schema_path()
        try:
            schema_sql = schema_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to read database schema at {schema_path}") from exc

        with self.conn:
            self.conn.executescript(schema_sql)

    def insert_event(
        self,
        event_type: str,
        source: str = "unknown",
        text: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
        session_id: str | None = None,
        project_id: int | None = None,
        privacy_level: str = "normal",
    ) -> int:
        now_ms = int(time.time() * 1000)
        timestamp_ms = now_ms if timestamp_ms is None else int(timestamp_ms)
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO memory_events (
                    timestamp_ms, event_type, source, session_id, project_id,
                    text, payload_json, privacy_level, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp_ms,
                    event_type,
                    source,
                    session_id,
                    project_id,
                    text,
                    payload_json,
                    privacy_level,
                    now_ms,
                ),
            )
        return int(cursor.lastrowid)

    def query_recent_events(
        self,
        limit: int = 20,
        event_type: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cursor = self.conn.execute(
            f"""
            SELECT id, timestamp_ms, event_type, source, session_id, project_id,
                   text, payload_json, privacy_level, created_at_ms
            FROM memory_events
            {where_sql}
            ORDER BY timestamp_ms DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [self._event_row_to_dict(row) for row in cursor.fetchall()]

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT id, timestamp_ms, event_type, source, session_id, project_id,
                   text, payload_json, privacy_level, created_at_ms
            FROM memory_events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()
        return self._event_row_to_dict(row) if row is not None else None

    def save_interaction(
        self,
        user_text: str,
        reply: str,
        emotion_tag: str | None = None,
        skill_called: str | None = None,
    ) -> int:
        timestamp_ms = int(time.time() * 1000)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO interactions (
                    timestamp, user_text, assistant_reply, emotion_tag, skill_called
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (timestamp_ms, user_text, reply, emotion_tag, skill_called),
            )
            interaction_id = int(cursor.lastrowid)
            self.conn.execute(
                """
                INSERT INTO memory_events (
                    timestamp_ms, event_type, source, text, payload_json,
                    privacy_level, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp_ms,
                    "interaction",
                    "memory",
                    user_text,
                    json.dumps(
                        {
                            "interaction_id": interaction_id,
                            "user_text": user_text,
                            "reply": reply,
                            "emotion_tag": emotion_tag,
                            "skill_called": skill_called,
                        },
                        ensure_ascii=False,
                    ),
                    "normal",
                    timestamp_ms,
                ),
            )
        return interaction_id

    def get_recent_interactions(self, limit: int = 10) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT id, timestamp, user_text, assistant_reply, emotion_tag, skill_called
            FROM interactions
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_emotion_summary(self, hours: int = 24) -> dict[str, Any]:
        now_ms = int(time.time() * 1000)
        since_ms = now_ms - int(hours * 60 * 60 * 1000)
        cursor = self.conn.execute(
            """
            SELECT emotion_tag, confidence, fatigue_score
            FROM emotions
            WHERE timestamp >= ? AND timestamp <= ?
            """,
            (since_ms, now_ms),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        if not rows:
            return {
                "count": 0,
                "avg_fatigue_score": 0.0,
                "max_confidence": 0.0,
                "top_emotion": None,
                "emotions_count": {},
            }

        emotions_count: dict[str, int] = {}
        for row in rows:
            emotion_tag = str(row["emotion_tag"])
            emotions_count[emotion_tag] = emotions_count.get(emotion_tag, 0) + 1

        top_emotion = max(emotions_count.items(), key=lambda item: item[1])[0]
        return {
            "count": len(rows),
            "avg_fatigue_score": sum(float(row["fatigue_score"]) for row in rows) / len(rows),
            "max_confidence": max(float(row["confidence"]) for row in rows),
            "top_emotion": top_emotion,
            "emotions_count": emotions_count,
        }

    def _event_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        event = dict(row)
        try:
            event["payload"] = json.loads(event.get("payload_json") or "{}")
        except json.JSONDecodeError:
            event["payload"] = {}
        return event


class Memory(XiaoAnMemoryStore):
    """Compatibility alias for older imports."""
