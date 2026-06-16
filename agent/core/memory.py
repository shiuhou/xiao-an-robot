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

    def insert_note(
        self,
        content: str,
        tags: list[str] | None = None,
        source: str = "tool_call",
        project_hint: str | None = None,
        project_id: int | None = None,
        timestamp_ms: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, int]:
        active_tags = tags or []
        payload = {
            "content": content,
            "tags": active_tags,
            "project_hint": project_hint,
            "project_id": project_id,
        }
        event_id = self.insert_event(
            event_type="note.added",
            source=source,
            text=content,
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
        tags_json = json.dumps(active_tags, ensure_ascii=False)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO notes (
                    event_id, timestamp_ms, content, tags_json, source,
                    project_hint, project_id, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    persisted_timestamp_ms,
                    content,
                    tags_json,
                    source,
                    project_hint,
                    project_id,
                    created_at_ms,
                ),
            )
        return {
            "event_id": event_id,
            "note_id": int(cursor.lastrowid),
        }

    def query_recent_notes(
        self,
        limit: int = 20,
        project_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_hint is not None:
            clauses.append("project_hint = ?")
            params.append(project_hint)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cursor = self.conn.execute(
            f"""
            SELECT id, event_id, timestamp_ms, content, tags_json, source,
                   project_hint, project_id, created_at_ms
            FROM notes
            {where_sql}
            ORDER BY timestamp_ms DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [self._note_row_to_dict(row) for row in cursor.fetchall()]

    def get_notes_summary(self, limit: int = 50) -> dict[str, Any]:
        rows = self.query_recent_notes(limit=limit)
        summary: dict[str, Any] = {
            "count": len(rows),
            "latest_content": None,
            "tag_count": {},
            "project_hint_count": {},
        }
        if not rows:
            return summary

        tag_count: dict[str, int] = {}
        project_hint_count: dict[str, int] = {}
        for row in rows:
            for tag in row.get("tags", []):
                tag_key = str(tag)
                tag_count[tag_key] = tag_count.get(tag_key, 0) + 1
            if row.get("project_hint") is not None:
                project_key = str(row["project_hint"])
                project_hint_count[project_key] = project_hint_count.get(project_key, 0) + 1

        summary.update({
            "latest_content": rows[0]["content"],
            "tag_count": tag_count,
            "project_hint_count": project_hint_count,
        })
        return summary

    def insert_summary(
        self,
        summary_type: str,
        content: str,
        title: str | None = None,
        date: str | None = None,
        source: str = "tool_call",
        project_hint: str | None = None,
        project_id: int | None = None,
        input_range_start_ms: int | None = None,
        input_range_end_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, int]:
        active_metadata = metadata or {}
        payload = {
            "summary_type": summary_type,
            "title": title,
            "date": date,
            "project_hint": project_hint,
            "metadata": active_metadata,
        }
        event_id = self.insert_event(
            event_type="summary.generated",
            source=source,
            text=content,
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
        metadata_json = json.dumps(active_metadata, ensure_ascii=False)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO summaries (
                    event_id, timestamp_ms, summary_type, title, content, date,
                    source, project_hint, project_id, input_range_start_ms,
                    input_range_end_ms, metadata_json, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    persisted_timestamp_ms,
                    summary_type,
                    title,
                    content,
                    date,
                    source,
                    project_hint,
                    project_id,
                    input_range_start_ms,
                    input_range_end_ms,
                    metadata_json,
                    created_at_ms,
                ),
            )
        return {
            "event_id": event_id,
            "summary_id": int(cursor.lastrowid),
        }

    def query_recent_summaries(
        self,
        limit: int = 20,
        summary_type: str | None = None,
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if summary_type is not None:
            clauses.append("summary_type = ?")
            params.append(summary_type)
        if date is not None:
            clauses.append("date = ?")
            params.append(date)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cursor = self.conn.execute(
            f"""
            SELECT id, event_id, timestamp_ms, summary_type, title, content, date,
                   source, project_hint, project_id, input_range_start_ms,
                   input_range_end_ms, metadata_json, created_at_ms
            FROM summaries
            {where_sql}
            ORDER BY timestamp_ms DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [self._summary_row_to_dict(row) for row in cursor.fetchall()]

    def get_summary_overview(self, limit: int = 50) -> dict[str, Any]:
        rows = self.query_recent_summaries(limit=limit)
        summary_type_count: dict[str, int] = {}
        for row in rows:
            summary_type = str(row["summary_type"])
            summary_type_count[summary_type] = summary_type_count.get(summary_type, 0) + 1
        return {
            "count": len(rows),
            "summary_type_count": summary_type_count,
            "latest_summary_type": rows[0]["summary_type"] if rows else None,
            "latest_title": rows[0]["title"] if rows else None,
        }

    def insert_reminder(
        self,
        message: str,
        due_at_ms: int | None = None,
        delay_seconds: int | float | None = None,
        source: str = "tool_call",
        project_hint: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, int]:
        if not message:
            raise ValueError("message is required")
        if due_at_ms is None and delay_seconds is None:
            raise ValueError("due_at_ms or delay_seconds is required")

        now_ms = int(time.time() * 1000)
        normalized_delay_seconds = delay_seconds
        if due_at_ms is None:
            delay_value = float(delay_seconds if delay_seconds is not None else 0)
            if delay_value <= 0:
                delay_value = 1.0
                normalized_delay_seconds = 1
            due_at_ms = now_ms + int(delay_value * 1000)
        else:
            due_at_ms = int(due_at_ms)

        active_metadata = metadata or {}
        payload = {
            "message": message,
            "due_at_ms": due_at_ms,
            "delay_seconds": normalized_delay_seconds,
            "project_hint": project_hint,
            "metadata": active_metadata,
        }
        event_id = self.insert_event(
            event_type="reminder.added",
            source=source,
            text=message,
            payload=payload,
            timestamp_ms=timestamp_ms,
            privacy_level=privacy_level,
        )
        metadata_json = json.dumps(active_metadata, ensure_ascii=False)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO reminders (
                    event_id, created_at_ms, updated_at_ms, due_at_ms,
                    fired_at_ms, status, message, source, project_hint,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    now_ms,
                    now_ms,
                    due_at_ms,
                    None,
                    "pending",
                    message,
                    source,
                    project_hint,
                    metadata_json,
                ),
            )
        return {
            "event_id": event_id,
            "reminder_id": int(cursor.lastrowid),
            "due_at_ms": int(due_at_ms),
        }

    def query_reminders(
        self,
        limit: int = 20,
        status: str | None = None,
        include_fired: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        elif not include_fired:
            clauses.append("status = ?")
            params.append("pending")

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cursor = self.conn.execute(
            f"""
            SELECT id, event_id, created_at_ms, updated_at_ms, due_at_ms,
                   fired_at_ms, status, message, source, project_hint,
                   metadata_json
            FROM reminders
            {where_sql}
            ORDER BY created_at_ms DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [self._reminder_row_to_dict(row) for row in cursor.fetchall()]

    def query_due_reminders(
        self,
        now_ms: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        cursor = self.conn.execute(
            """
            SELECT id, event_id, created_at_ms, updated_at_ms, due_at_ms,
                   fired_at_ms, status, message, source, project_hint,
                   metadata_json
            FROM reminders
            WHERE status = ? AND due_at_ms <= ?
            ORDER BY due_at_ms ASC, id ASC
            LIMIT ?
            """,
            ("pending", now_ms, int(limit)),
        )
        return [self._reminder_row_to_dict(row) for row in cursor.fetchall()]

    def mark_reminder_fired(
        self,
        reminder_id: int,
        fired_at_ms: int | None = None,
        source: str = "reminder_scheduler",
        privacy_level: str = "normal",
    ) -> dict[str, Any]:
        reminder = self._get_reminder_row(reminder_id)
        if reminder is None:
            return {"ok": False, "reason": "not_found", "reminder_id": reminder_id}

        fired_at_ms = int(time.time() * 1000) if fired_at_ms is None else int(fired_at_ms)
        with self.conn:
            self.conn.execute(
                """
                UPDATE reminders
                SET status = ?, fired_at_ms = ?, updated_at_ms = ?
                WHERE id = ?
                """,
                ("fired", fired_at_ms, fired_at_ms, int(reminder_id)),
            )
        payload = {
            "reminder_id": int(reminder_id),
            "message": reminder["message"],
            "due_at_ms": reminder["due_at_ms"],
            "fired_at_ms": fired_at_ms,
        }
        event_id = self.insert_event(
            event_type="reminder.fired",
            source=source,
            text=reminder["message"],
            payload=payload,
            timestamp_ms=fired_at_ms,
            privacy_level=privacy_level,
        )
        return {
            "ok": True,
            "event_id": event_id,
            "reminder_id": int(reminder_id),
        }

    def cancel_reminder(
        self,
        reminder_id: int | None = None,
        message_contains: str | None = None,
        source: str = "tool_call",
        timestamp_ms: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, Any]:
        reminder = None
        if reminder_id is not None:
            reminder = self._get_reminder_row(int(reminder_id), status="pending")
        elif message_contains:
            reminder = self.conn.execute(
                """
                SELECT id, event_id, created_at_ms, updated_at_ms, due_at_ms,
                       fired_at_ms, status, message, source, project_hint,
                       metadata_json
                FROM reminders
                WHERE status = ? AND message LIKE ?
                ORDER BY created_at_ms DESC, id DESC
                LIMIT 1
                """,
                ("pending", f"%{message_contains}%"),
            ).fetchone()

        if reminder is None:
            return {"ok": False, "reason": "not_found"}

        now_ms = int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms)
        with self.conn:
            self.conn.execute(
                """
                UPDATE reminders
                SET status = ?, updated_at_ms = ?
                WHERE id = ?
                """,
                ("cancelled", now_ms, int(reminder["id"])),
            )
        payload = {
            "reminder_id": int(reminder["id"]),
            "message": reminder["message"],
        }
        event_id = self.insert_event(
            event_type="reminder.cancelled",
            source=source,
            text=reminder["message"],
            payload=payload,
            timestamp_ms=now_ms,
            privacy_level=privacy_level,
        )
        return {
            "ok": True,
            "event_id": event_id,
            "reminder_id": int(reminder["id"]),
            "message": reminder["message"],
        }

    def get_reminders_summary(self, limit: int = 50) -> dict[str, Any]:
        rows = self.query_reminders(limit=limit, include_fired=True)
        status_count: dict[str, int] = {}
        for row in rows:
            status = str(row["status"])
            status_count[status] = status_count.get(status, 0) + 1
        return {
            "count": len(rows),
            "pending_count": status_count.get("pending", 0),
            "fired_count": status_count.get("fired", 0),
            "cancelled_count": status_count.get("cancelled", 0),
            "latest_message": rows[0]["message"] if rows else None,
            "status_count": status_count,
        }

    def insert_task(
        self,
        title: str,
        description: str | None = None,
        due_at_ms: int | None = None,
        due_text: str | None = None,
        priority: str = "normal",
        source: str = "tool_call",
        project_hint: str | None = None,
        project_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, int]:
        if not title:
            raise ValueError("title is required")
        priority = priority if priority in {"low", "normal", "high"} else "normal"
        now_ms = int(time.time() * 1000)
        active_metadata = metadata or {}
        payload = {
            "title": title,
            "description": description,
            "due_at_ms": due_at_ms,
            "due_text": due_text,
            "priority": priority,
            "project_hint": project_hint,
            "project_id": project_id,
            "metadata": active_metadata,
        }
        event_id = self.insert_event(
            event_type="task.added",
            source=source,
            text=title,
            payload=payload,
            timestamp_ms=timestamp_ms,
            project_id=project_id,
            privacy_level=privacy_level,
        )
        metadata_json = json.dumps(active_metadata, ensure_ascii=False)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO tasks (
                    event_id, created_at_ms, updated_at_ms, title, description,
                    due_at_ms, due_text, status, priority, source, project_hint,
                    project_id, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    now_ms,
                    now_ms,
                    title,
                    description,
                    due_at_ms,
                    due_text,
                    "pending",
                    priority,
                    source,
                    project_hint,
                    project_id,
                    metadata_json,
                ),
            )
        return {
            "event_id": event_id,
            "task_id": int(cursor.lastrowid),
        }

    def query_tasks(
        self,
        limit: int = 20,
        status: str | None = None,
        project_hint: str | None = None,
        include_done: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        elif not include_done:
            clauses.append("status = ?")
            params.append("pending")
        if project_hint is not None:
            clauses.append("project_hint = ?")
            params.append(project_hint)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cursor = self.conn.execute(
            f"""
            SELECT id, event_id, created_at_ms, updated_at_ms, title,
                   description, due_at_ms, due_text, status, priority,
                   source, project_hint, project_id, metadata_json
            FROM tasks
            {where_sql}
            ORDER BY created_at_ms DESC, id DESC
            LIMIT ?
            """,
            params,
        )
        return [self._task_row_to_dict(row) for row in cursor.fetchall()]

    def complete_task(
        self,
        task_id: int | None = None,
        title_contains: str | None = None,
        source: str = "tool_call",
        timestamp_ms: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, Any]:
        return self._update_task_status(
            task_id=task_id,
            title_contains=title_contains,
            new_status="done",
            event_type="task.completed",
            source=source,
            timestamp_ms=timestamp_ms,
            privacy_level=privacy_level,
        )

    def cancel_task(
        self,
        task_id: int | None = None,
        title_contains: str | None = None,
        source: str = "tool_call",
        timestamp_ms: int | None = None,
        privacy_level: str = "normal",
    ) -> dict[str, Any]:
        return self._update_task_status(
            task_id=task_id,
            title_contains=title_contains,
            new_status="cancelled",
            event_type="task.cancelled",
            source=source,
            timestamp_ms=timestamp_ms,
            privacy_level=privacy_level,
        )

    def get_tasks_summary(self, limit: int = 50) -> dict[str, Any]:
        rows = self.query_tasks(limit=limit, include_done=True)
        status_count: dict[str, int] = {}
        priority_count: dict[str, int] = {}
        project_hint_count: dict[str, int] = {}
        for row in rows:
            status = str(row["status"])
            priority = str(row["priority"])
            status_count[status] = status_count.get(status, 0) + 1
            priority_count[priority] = priority_count.get(priority, 0) + 1
            if row.get("project_hint") is not None:
                project_key = str(row["project_hint"])
                project_hint_count[project_key] = project_hint_count.get(project_key, 0) + 1
        return {
            "count": len(rows),
            "pending_count": status_count.get("pending", 0),
            "done_count": status_count.get("done", 0),
            "cancelled_count": status_count.get("cancelled", 0),
            "high_priority_count": priority_count.get("high", 0),
            "latest_task_title": rows[0]["title"] if rows else None,
            "status_count": status_count,
            "priority_count": priority_count,
            "project_hint_count": project_hint_count,
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

    def _note_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        note = dict(row)
        try:
            tags = json.loads(note.get("tags_json") or "[]")
        except json.JSONDecodeError:
            tags = []
        note["tags"] = tags if isinstance(tags, list) else []
        return note

    def _summary_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        summary = dict(row)
        try:
            metadata = json.loads(summary.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            metadata = {}
        summary["metadata"] = metadata if isinstance(metadata, dict) else {}
        return summary

    def _reminder_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        reminder = dict(row)
        try:
            metadata = json.loads(reminder.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            metadata = {}
        reminder["metadata"] = metadata if isinstance(metadata, dict) else {}
        return reminder

    def _task_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        task = dict(row)
        try:
            metadata = json.loads(task.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            metadata = {}
        task["metadata"] = metadata if isinstance(metadata, dict) else {}
        return task

    def _get_reminder_row(self, reminder_id: int, status: str | None = None) -> sqlite3.Row | None:
        clauses = ["id = ?"]
        params: list[Any] = [int(reminder_id)]
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        return self.conn.execute(
            f"""
            SELECT id, event_id, created_at_ms, updated_at_ms, due_at_ms,
                   fired_at_ms, status, message, source, project_hint,
                   metadata_json
            FROM reminders
            WHERE {' AND '.join(clauses)}
            """,
            params,
        ).fetchone()

    def _get_task_row(self, task_id: int, status: str | None = None) -> sqlite3.Row | None:
        clauses = ["id = ?"]
        params: list[Any] = [int(task_id)]
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        return self.conn.execute(
            f"""
            SELECT id, event_id, created_at_ms, updated_at_ms, title,
                   description, due_at_ms, due_text, status, priority,
                   source, project_hint, project_id, metadata_json
            FROM tasks
            WHERE {' AND '.join(clauses)}
            """,
            params,
        ).fetchone()

    def _find_pending_task_by_title(self, title_contains: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT id, event_id, created_at_ms, updated_at_ms, title,
                   description, due_at_ms, due_text, status, priority,
                   source, project_hint, project_id, metadata_json
            FROM tasks
            WHERE status = ? AND title LIKE ?
            ORDER BY created_at_ms DESC, id DESC
            LIMIT 1
            """,
            ("pending", f"%{title_contains}%"),
        ).fetchone()

    def _update_task_status(
        self,
        task_id: int | None,
        title_contains: str | None,
        new_status: str,
        event_type: str,
        source: str,
        timestamp_ms: int | None,
        privacy_level: str,
    ) -> dict[str, Any]:
        task = None
        if task_id is not None:
            task = self._get_task_row(int(task_id), status="pending")
        elif title_contains:
            task = self._find_pending_task_by_title(title_contains)

        if task is None:
            return {"ok": False, "reason": "not_found"}

        now_ms = int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms)
        previous_status = task["status"]
        with self.conn:
            self.conn.execute(
                """
                UPDATE tasks
                SET status = ?, updated_at_ms = ?
                WHERE id = ?
                """,
                (new_status, now_ms, int(task["id"])),
            )
        payload = {
            "task_id": int(task["id"]),
            "title": task["title"],
            "previous_status": previous_status,
            "status": new_status,
        }
        event_id = self.insert_event(
            event_type=event_type,
            source=source,
            text=task["title"],
            payload=payload,
            timestamp_ms=now_ms,
            project_id=task["project_id"],
            privacy_level=privacy_level,
        )
        return {
            "ok": True,
            "event_id": event_id,
            "task_id": int(task["id"]),
            "title": task["title"],
        }

    def _top_count_key(self, counts: dict[str, int]) -> str | None:
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]


class Memory(XiaoAnMemoryStore):
    """Compatibility alias for older imports."""
