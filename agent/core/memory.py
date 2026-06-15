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

    def insert_work_activity(
        self,
        source: str = "unknown",
        app_name: str = "",
        window_title: str = "",
        activity_type: str = "unknown",
        project_hint: str | None = None,
        confidence: float = 0.0,
        duration_seconds: float | None = None,
        timestamp_ms: int | None = None,
        project_id: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, int]:
        event_text = f"{app_name} | {activity_type} | {project_hint}"
        payload = {
            "app_name": app_name,
            "window_title": window_title,
            "activity_type": activity_type,
            "project_hint": project_hint,
            "confidence": confidence,
            "duration_seconds": duration_seconds,
        }
        event_id = self.insert_event(
            event_type="work.activity",
            source=source,
            text=event_text,
            payload=payload,
            timestamp_ms=timestamp_ms,
            project_id=project_id,
            privacy_level=privacy_level,
        )
        event = self.get_event(event_id)
        persisted_timestamp_ms = (
            int(event["timestamp_ms"])
            if event is not None
            else int(time.time() * 1000)
        )
        created_at_ms = int(time.time() * 1000)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO work_activities (
                    event_id, timestamp_ms, source, app_name, window_title,
                    activity_type, project_hint, project_id, confidence,
                    duration_seconds, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    persisted_timestamp_ms,
                    source,
                    app_name,
                    window_title,
                    activity_type,
                    project_hint,
                    project_id,
                    confidence,
                    duration_seconds,
                    created_at_ms,
                ),
            )
        return {
            "event_id": event_id,
            "work_activity_id": int(cursor.lastrowid),
        }

    def query_recent_work_activities(
        self,
        limit: int = 20,
        activity_type: str | None = None,
        project_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if activity_type is not None:
            clauses.append("activity_type = ?")
            params.append(activity_type)
        if project_hint is not None:
            clauses.append("project_hint = ?")
            params.append(project_hint)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cursor = self.conn.execute(
            f"""
            SELECT id, event_id, timestamp_ms, source, app_name, window_title,
                   activity_type, project_hint, project_id, confidence,
                   duration_seconds, created_at_ms
            FROM work_activities
            {where_sql}
            ORDER BY timestamp_ms DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_recent_work_summary(self, limit: int = 50) -> dict[str, Any]:
        rows = self.query_recent_work_activities(limit=limit)
        summary: dict[str, Any] = {
            "count": len(rows),
            "latest_activity_type": None,
            "latest_app_name": None,
            "latest_project_hint": None,
            "top_activity_type": None,
            "top_app_name": None,
            "activity_type_count": {},
            "app_count": {},
            "project_hint_count": {},
        }
        if not rows:
            return summary

        latest = rows[0]
        activity_type_count: dict[str, int] = {}
        app_count: dict[str, int] = {}
        project_hint_count: dict[str, int] = {}
        for row in rows:
            activity_type = str(row["activity_type"])
            app_name = str(row["app_name"])
            project_hint = row["project_hint"]
            activity_type_count[activity_type] = activity_type_count.get(activity_type, 0) + 1
            app_count[app_name] = app_count.get(app_name, 0) + 1
            if project_hint is not None:
                project_key = str(project_hint)
                project_hint_count[project_key] = project_hint_count.get(project_key, 0) + 1

        summary.update({
            "latest_activity_type": latest["activity_type"],
            "latest_app_name": latest["app_name"],
            "latest_project_hint": latest["project_hint"],
            "top_activity_type": self._top_count_key(activity_type_count),
            "top_app_name": self._top_count_key(app_count),
            "activity_type_count": activity_type_count,
            "app_count": app_count,
            "project_hint_count": project_hint_count,
        })
        return summary

    def insert_tool_run(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        status: str = "success",
        error: str | None = None,
        source_event_type: str | None = None,
        timestamp_ms: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, int]:
        payload = {
            "tool_name": tool_name,
            "arguments": arguments or {},
            "result": result or {},
            "status": status,
            "error": error,
            "source_event_type": source_event_type,
        }
        event_id = self.insert_event(
            event_type="tool.run",
            source="action_executor",
            text=f"{tool_name} status={status}",
            payload=payload,
            timestamp_ms=timestamp_ms,
            privacy_level=privacy_level,
        )
        event = self.get_event(event_id)
        persisted_timestamp_ms = (
            int(event["timestamp_ms"])
            if event is not None
            else int(time.time() * 1000)
        )
        created_at_ms = int(time.time() * 1000)
        arguments_json = json.dumps(arguments or {}, ensure_ascii=False)
        result_json = json.dumps(result or {}, ensure_ascii=False)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO tool_runs (
                    event_id, timestamp_ms, source_event_type, tool_name,
                    arguments_json, result_json, status, error, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    persisted_timestamp_ms,
                    source_event_type,
                    tool_name,
                    arguments_json,
                    result_json,
                    status,
                    error,
                    created_at_ms,
                ),
            )
        return {
            "event_id": event_id,
            "tool_run_id": int(cursor.lastrowid),
        }

    def query_recent_tool_runs(
        self,
        limit: int = 20,
        tool_name: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if tool_name is not None:
            clauses.append("tool_name = ?")
            params.append(tool_name)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cursor = self.conn.execute(
            f"""
            SELECT id, event_id, timestamp_ms, source_event_type, tool_name,
                   arguments_json, result_json, status, error, created_at_ms
            FROM tool_runs
            {where_sql}
            ORDER BY timestamp_ms DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [self._tool_run_row_to_dict(row) for row in cursor.fetchall()]

    def get_tool_run_summary(self, limit: int = 50) -> dict[str, Any]:
        rows = self.query_recent_tool_runs(limit=limit)
        tool_count: dict[str, int] = {}
        status_count: dict[str, int] = {}
        for row in rows:
            tool_name = str(row["tool_name"])
            status = str(row["status"])
            tool_count[tool_name] = tool_count.get(tool_name, 0) + 1
            status_count[status] = status_count.get(status, 0) + 1

        return {
            "count": len(rows),
            "success_count": status_count.get("success", 0),
            "failed_count": status_count.get("failed", 0),
            "skipped_count": status_count.get("skipped", 0),
            "latest_tool": rows[0]["tool_name"] if rows else None,
            "tool_count": tool_count,
            "status_count": status_count,
        }

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

    def _tool_run_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        tool_run = dict(row)
        try:
            tool_run["arguments"] = json.loads(tool_run.get("arguments_json") or "{}")
        except json.JSONDecodeError:
            tool_run["arguments"] = {}
        try:
            tool_run["result"] = json.loads(tool_run.get("result_json") or "{}")
        except json.JSONDecodeError:
            tool_run["result"] = {}
        return tool_run

    def _top_count_key(self, counts: dict[str, int]) -> str | None:
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]


class Memory(XiaoAnMemoryStore):
    """Compatibility alias for older imports."""
