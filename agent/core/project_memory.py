"""Legacy project-context helpers built on the Local Event Store."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.core.memory import XiaoAnMemoryStore


class ProjectMemoryService:
    """Record and retrieve compatibility context without exposing storage details."""

    _SCOPE_ALIASES = {
        "notes": "notes",
        "tasks": "tasks",
        "reminders": "reminders",
        "summaries": "summaries",
        "work": "work_activities",
        "work_activities": "work_activities",
        "tools": "tool_runs",
        "tool_runs": "tool_runs",
        "care": "care_events",
        "care_events": "care_events",
        "events": "memory_events",
        "memory_events": "memory_events",
    }

    def __init__(
        self,
        memory_store: Any | None = None,
        db_path: str | None = None,
    ):
        self._owns_memory_store = memory_store is None
        self.memory_store = memory_store or XiaoAnMemoryStore(db_path=db_path)

    def close(self) -> None:
        if self._owns_memory_store:
            close = getattr(self.memory_store, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> "ProjectMemoryService":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def record_note(
        self,
        text: str,
        source: str = "tool",
        session_id: str | None = None,
        payload: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, int]:
        if not text:
            raise ValueError("text is required")
        active_payload = self._json_safe_dict(payload)
        return self.memory_store.insert_note(
            content=text,
            tags=self._normalize_tags(tags),
            source=source,
            project_hint=active_payload.get("project_hint"),
            project_id=active_payload.get("project_id"),
            timestamp_ms=active_payload.get("timestamp_ms"),
            privacy_level=active_payload.get("privacy_level", "normal"),
            event_type="note.add",
            event_payload=active_payload,
            session_id=session_id,
        )

    def search_notes(
        self,
        keyword: str | None = None,
        limit: int = 5,
        project_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.memory_store.query_recent_notes(
            limit=max(0, int(limit)),
            project_hint=project_hint,
            keyword=self._optional_text(keyword),
        )
        return [
            {
                "id": row.get("id"),
                "timestamp_ms": row.get("timestamp_ms"),
                "content": row.get("content"),
                "tags": list(row.get("tags") or []),
                "source": row.get("source"),
                "project_hint": row.get("project_hint"),
            }
            for row in rows
        ]

    def record_work_activity(
        self,
        text: str,
        source: str = "tool",
        session_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        if not text:
            raise ValueError("text is required")
        active_payload = self._json_safe_dict(payload)
        return self.memory_store.insert_work_activity(
            source=source,
            app_name=str(active_payload.get("app_name", "")),
            window_title=str(active_payload.get("window_title") or text),
            activity_type=str(active_payload.get("activity_type", "work_context")),
            project_hint=active_payload.get("project_hint"),
            confidence=self._float_or_default(active_payload.get("confidence"), 0.0),
            duration_seconds=self._optional_float(active_payload.get("duration_seconds")),
            timestamp_ms=active_payload.get("timestamp_ms"),
            project_id=active_payload.get("project_id"),
            privacy_level=active_payload.get("privacy_level", "normal"),
            event_type="work_context.record",
            event_text=text,
            event_payload=active_payload,
            session_id=session_id,
        )

    def query_work_activities(
        self,
        keyword: str | None = None,
        project_hint: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        rows = self.memory_store.query_recent_work_activities(
            limit=max(0, int(limit)),
            project_hint=project_hint,
            keyword=self._optional_text(keyword),
        )
        return [
            {
                "id": row.get("id"),
                "timestamp_ms": row.get("timestamp_ms"),
                "source": row.get("source"),
                "app_name": row.get("app_name"),
                "window_title": row.get("window_title"),
                "activity_type": row.get("activity_type"),
                "project_hint": row.get("project_hint"),
                "confidence": row.get("confidence"),
                "duration_seconds": row.get("duration_seconds"),
            }
            for row in rows
        ]

    def record_summary(
        self,
        text: str,
        source: str = "tool",
        session_id: str | None = None,
        payload: dict[str, Any] | None = None,
        summary_type: str = "daily",
    ) -> dict[str, int]:
        if not text:
            raise ValueError("text is required")
        active_payload = self._json_safe_dict(payload)
        event_type = (
            "summary.daily"
            if summary_type == "daily"
            else f"summary.{summary_type}"
        )
        return self.memory_store.insert_summary(
            summary_type=summary_type,
            content=text,
            title=active_payload.get("title"),
            date=active_payload.get("date"),
            source=source,
            project_hint=active_payload.get("project_hint"),
            project_id=active_payload.get("project_id"),
            input_range_start_ms=active_payload.get("input_range_start_ms"),
            input_range_end_ms=active_payload.get("input_range_end_ms"),
            metadata=active_payload,
            timestamp_ms=active_payload.get("timestamp_ms"),
            privacy_level=active_payload.get("privacy_level", "normal"),
            event_type=event_type,
            event_payload=active_payload,
            session_id=session_id,
        )

    def query_summaries(
        self,
        date: str | None = None,
        summary_type: str | None = None,
        keyword: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        rows = self.memory_store.query_recent_summaries(
            limit=max(0, int(limit)),
            summary_type=self._optional_text(summary_type),
            date=self._optional_text(date),
            keyword=self._optional_text(keyword),
        )
        return [
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "summary_type": row.get("summary_type"),
                "date": row.get("date"),
                "created_at_ms": row.get("created_at_ms"),
                "content_preview": self._preview(row.get("content")),
            }
            for row in rows
        ]

    def record_tool_run(
        self,
        tool_name: str,
        arguments: Any = None,
        result: Any = None,
        ok: bool = True,
        source: str = "openclaw",
        source_event_type: str | None = None,
        session_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if not tool_name:
            raise ValueError("tool_name is required")
        safe_arguments = self._json_safe(arguments if arguments is not None else {})
        safe_result = self._json_safe(result if result is not None else {})
        status = "success" if ok else "failed"
        stored = self.memory_store.insert_tool_run(
            tool_name=tool_name,
            arguments=safe_arguments,
            result=safe_result,
            status=status,
            error=str(error) if error is not None else None,
            source_event_type=source_event_type,
            source=source,
            session_id=session_id,
        )
        return {
            "ok": bool(ok),
            "status": status,
            "error": str(error) if error is not None else None,
            **stored,
        }

    def record_task(
        self,
        title: str,
        description: str | None = None,
        due_at_ms: int | None = None,
        due_text: str | None = None,
        priority: str = "normal",
        source: str = "openclaw",
        project_hint: str | None = None,
        project_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
    ) -> dict[str, int]:
        normalized_title = str(title).strip() if title is not None else ""
        if not normalized_title:
            raise ValueError("missing_task_title")
        return self.memory_store.insert_task(
            title=normalized_title,
            description=description,
            due_at_ms=due_at_ms,
            due_text=due_text,
            priority=priority,
            source=source,
            project_hint=project_hint,
            project_id=project_id,
            metadata=self._json_safe_dict(metadata),
            timestamp_ms=timestamp_ms,
        )

    def query_tasks(
        self,
        limit: int = 20,
        status: str | None = None,
        project_hint: str | None = None,
        include_done: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_status = str(status).strip().lower() if status is not None else None
        if normalized_status == "all":
            normalized_status = None
            include_done = True
        elif normalized_status not in {None, "pending", "done", "cancelled"}:
            raise ValueError("invalid_task_status")
        return self.memory_store.query_tasks(
            limit=max(0, int(limit)),
            status=normalized_status,
            project_hint=project_hint,
            include_done=bool(include_done),
        )

    def complete_task(
        self,
        task_id: int | None = None,
        title_contains: str | None = None,
        source: str = "openclaw",
        timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        result = self.memory_store.complete_task(
            task_id=task_id,
            title_contains=title_contains,
            source=source,
            timestamp_ms=timestamp_ms,
        )
        if not result.get("ok", False):
            return {"ok": False, "error": "task_not_found", **result}
        return {**result, "status": "done"}

    def cancel_task(
        self,
        task_id: int | None = None,
        title_contains: str | None = None,
        source: str = "openclaw",
        timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        result = self.memory_store.cancel_task(
            task_id=task_id,
            title_contains=title_contains,
            source=source,
            timestamp_ms=timestamp_ms,
        )
        if not result.get("ok", False):
            return {"ok": False, "error": "task_not_found", **result}
        return {**result, "status": "cancelled"}

    def record_reminder(
        self,
        message: str,
        due_at_ms: int | None = None,
        delay_seconds: int | float | None = None,
        due_text: str | None = None,
        date: str | None = None,
        source: str = "openclaw",
        project_hint: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
    ) -> dict[str, int]:
        normalized_message = str(message).strip() if message is not None else ""
        if not normalized_message:
            raise ValueError("missing_reminder_message")

        normalized_due_at_ms = due_at_ms
        if normalized_due_at_ms is None and delay_seconds is None and date:
            normalized_due_at_ms = self._parse_date_ms(date)
        if normalized_due_at_ms is None and delay_seconds is None:
            raise ValueError("missing_reminder_time")

        active_metadata = self._json_safe_dict(metadata)
        if due_text is not None:
            active_metadata["due_text"] = str(due_text)
        if date is not None:
            active_metadata["date"] = str(date)
        return self.memory_store.insert_reminder(
            message=normalized_message,
            due_at_ms=normalized_due_at_ms,
            delay_seconds=delay_seconds,
            source=source,
            project_hint=project_hint,
            metadata=active_metadata,
            timestamp_ms=timestamp_ms,
        )

    def query_reminders(
        self,
        limit: int = 20,
        status: str | None = None,
        include_fired: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_status = str(status).strip().lower() if status is not None else None
        if normalized_status == "all":
            normalized_status = None
            include_fired = True
        elif normalized_status not in {None, "pending", "fired", "cancelled"}:
            raise ValueError("invalid_reminder_status")
        return self.memory_store.query_reminders(
            limit=max(0, int(limit)),
            status=normalized_status,
            include_fired=bool(include_fired),
        )

    def get_reminders_summary(self, limit: int = 50) -> dict[str, Any]:
        return self.memory_store.get_reminders_summary(limit=max(0, int(limit)))

    def cancel_reminder(
        self,
        reminder_id: int | None = None,
        message_contains: str | None = None,
        source: str = "openclaw",
        timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        result = self.memory_store.cancel_reminder(
            reminder_id=reminder_id,
            message_contains=message_contains,
            source=source,
            timestamp_ms=timestamp_ms,
        )
        if not result.get("ok", False):
            return {"ok": False, "error": "reminder_not_found", **result}
        return {**result, "status": "cancelled"}

    def get_recent_project_context(
        self,
        limit: int = 5,
        scope: str | None = None,
    ) -> dict[str, Any]:
        active_limit = min(5, max(0, int(limit)))
        selected_scope = self._normalize_scope(scope)
        context: dict[str, Any] = {}

        if selected_scope in (None, "notes"):
            notes = self.memory_store.query_recent_notes(limit=active_limit)
            notes_summary = self.memory_store.get_notes_summary(limit=active_limit)
            context["recent_notes"] = [
                {
                    "timestamp_ms": row.get("timestamp_ms"),
                    "content": self._preview(row.get("content")),
                    "tags": list(row.get("tags") or []),
                    "project_hint": row.get("project_hint"),
                }
                for row in notes
            ]
            context["notes_summary"] = {
                "count": notes_summary.get("count", len(notes)),
                "latest_content": self._preview(notes_summary.get("latest_content")),
                "tag_count": notes_summary.get("tag_count", {}),
                "project_hint_count": notes_summary.get("project_hint_count", {}),
            }
            context["notes_count"] = context["notes_summary"]["count"]
        if selected_scope in (None, "tasks"):
            tasks = self.memory_store.query_tasks(
                limit=active_limit,
                status="pending",
            )
            context["recent_tasks"] = [
                {
                    "id": row.get("id"),
                    "title": self._preview(row.get("title")),
                    "description": self._preview(row.get("description")),
                    "due_at_ms": row.get("due_at_ms"),
                    "due_text": row.get("due_text"),
                    "status": row.get("status"),
                    "priority": row.get("priority"),
                    "project_hint": row.get("project_hint"),
                }
                for row in tasks
            ]
            context["tasks_summary"] = self.memory_store.get_tasks_summary(
                limit=max(active_limit, 50),
            )
        if selected_scope in (None, "reminders"):
            reminders = self.memory_store.query_reminders(
                limit=active_limit,
                status="pending",
            )
            context["recent_reminders"] = [
                {
                    "id": row.get("id"),
                    "due_at_ms": row.get("due_at_ms"),
                    "status": row.get("status"),
                    "message": self._preview(row.get("message")),
                    "project_hint": row.get("project_hint"),
                }
                for row in reminders
            ]
            context["reminders_summary"] = self.memory_store.get_reminders_summary(
                limit=max(active_limit, 50),
            )
        if selected_scope in (None, "summaries"):
            summaries = self.memory_store.query_recent_summaries(limit=active_limit)
            overview = self.memory_store.get_summary_overview(limit=active_limit)
            context["recent_summaries"] = [
                {
                    "timestamp_ms": row.get("timestamp_ms"),
                    "summary_type": row.get("summary_type"),
                    "title": row.get("title"),
                    "date": row.get("date"),
                    "content_preview": self._preview(row.get("content")),
                }
                for row in summaries
            ]
            context["summary_overview"] = {
                "count": overview.get("count", len(summaries)),
                "latest_summary_type": overview.get("latest_summary_type"),
                "latest_summary_title": overview.get("latest_title"),
                "summary_type_count": overview.get("summary_type_count", {}),
            }
        if selected_scope in (None, "work_activities"):
            activities = self.memory_store.query_recent_work_activities(limit=active_limit)
            work_summary = self.memory_store.get_recent_work_summary(limit=active_limit)
            context["recent_work_activities"] = [
                {
                    "timestamp_ms": row.get("timestamp_ms"),
                    "app_name": row.get("app_name"),
                    "window_title": self._preview(row.get("window_title")),
                    "activity_type": row.get("activity_type"),
                    "project_hint": row.get("project_hint"),
                    "duration_seconds": row.get("duration_seconds"),
                }
                for row in activities
            ]
            context["work_summary"] = {
                "count": work_summary.get("count", len(activities)),
                "latest_activity_type": work_summary.get("latest_activity_type"),
                "latest_app_name": work_summary.get("latest_app_name"),
                "latest_project_hint": work_summary.get("latest_project_hint"),
                "top_activity_type": work_summary.get("top_activity_type"),
                "top_app_name": work_summary.get("top_app_name"),
            }
        if selected_scope in (None, "tool_runs"):
            tool_runs = self.memory_store.query_recent_tool_runs(limit=active_limit)
            context["recent_tool_runs"] = [
                {
                    "timestamp_ms": row.get("timestamp_ms"),
                    "tool_name": row.get("tool_name"),
                    "status": row.get("status"),
                    "error": row.get("error"),
                    "source_event_type": row.get("source_event_type"),
                }
                for row in tool_runs
            ]
            context["tool_run_summary"] = self.memory_store.get_tool_run_summary(
                limit=active_limit,
            )
        if selected_scope in (None, "care_events"):
            care_events: list[dict[str, Any]] = []
            for event_type in (
                "companion.request",
                "emotion.intervention",
                "robot.care_action",
            ):
                care_events.extend(self.memory_store.query_recent_events(
                    limit=active_limit,
                    event_type=event_type,
                ))
            care_events.sort(
                key=lambda item: (item.get("timestamp_ms", 0), item.get("id", 0)),
                reverse=True,
            )
            context["recent_care_events"] = [
                {
                    "timestamp_ms": event.get("timestamp_ms"),
                    "event_type": event.get("event_type"),
                    "source": event.get("source"),
                    "text": self._preview(event.get("text")),
                }
                for event in care_events[:active_limit]
            ]
        if selected_scope in (None, "memory_events"):
            events = self.memory_store.query_recent_events(limit=active_limit)
            context["recent_memory_events"] = [
                {
                    "timestamp_ms": event.get("timestamp_ms"),
                    "event_type": event.get("event_type"),
                    "source": event.get("source"),
                    "text": self._preview(event.get("text")),
                }
                for event in events
            ]
            context["memory_events_count"] = len(events)

        context["project_memory_summary"] = {
            "notes_count": context.get("notes_count", 0),
            "tasks_count": context.get("tasks_summary", {}).get("count", 0),
            "pending_tasks_count": context.get("tasks_summary", {}).get(
                "pending_count",
                0,
            ),
            "reminders_count": context.get("reminders_summary", {}).get("count", 0),
            "pending_reminders_count": context.get("reminders_summary", {}).get(
                "pending_count",
                0,
            ),
            "work_activities_count": context.get("work_summary", {}).get("count", 0),
            "summaries_count": context.get("summary_overview", {}).get("count", 0),
            "tool_runs_count": context.get("tool_run_summary", {}).get("count", 0),
            "care_events_count": len(context.get("recent_care_events", [])),
            "latest_summary_title": context.get("summary_overview", {}).get(
                "latest_summary_title",
            ),
        }

        return {
            "scope": selected_scope or "all",
            "limit": active_limit,
            **context,
        }

    def _normalize_scope(self, scope: str | None) -> str | None:
        if scope is None:
            return None
        normalized = self._SCOPE_ALIASES.get(str(scope).strip().lower())
        if normalized is None:
            raise ValueError(f"unsupported project memory scope: {scope}")
        return normalized

    def _preview(self, value: Any, limit: int = 160) -> str | None:
        if value is None:
            return None
        text = str(value)
        if len(text) <= limit:
            return text
        return f"{text[:limit - 3]}..."

    def _json_safe_dict(self, value: dict[str, Any] | None) -> dict[str, Any]:
        safe_value = self._json_safe(value or {})
        return safe_value if isinstance(safe_value, dict) else {}

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        return str(value)

    def _normalize_tags(self, tags: list[str] | None) -> list[str]:
        return [str(tag) for tag in (tags or [])]

    def _float_or_default(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _parse_date_ms(self, value: str) -> int | None:
        text = str(value).strip()
        if not text:
            return None
        try:
            normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
            return int(datetime.fromisoformat(normalized).timestamp() * 1000)
        except ValueError:
            return None
