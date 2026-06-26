"""Assemble optional compatibility context for OpenClaw events."""

from __future__ import annotations

from typing import Any

from agent.core.context_policy import ContextInjectionPolicy
from agent.core.project_memory import ProjectMemoryService


class ContextBuilder:
    """Build event context without deciding how OpenClaw should respond."""

    def __init__(
        self,
        memory_store: Any | None = None,
        policy: ContextInjectionPolicy | None = None,
        work_limit: int = 20,
    ):
        self.memory_store = memory_store
        self.project_memory = (
            ProjectMemoryService(memory_store=memory_store)
            if memory_store is not None
            else None
        )
        self.policy = policy or ContextInjectionPolicy()
        self.work_limit = work_limit

    def build_for_text(
        self,
        text: str | None,
        base_context: dict | None = None,
        event_type: str | None = None,
        source: str | None = None,
    ) -> dict:
        context = dict(base_context or {})
        decision = self.policy.decide_for_text(text)
        context["context_policy"] = {
            "needs_work_context": decision.needs_work_context,
            "needs_notes_context": decision.needs_notes_context,
            "needs_tasks_context": decision.needs_tasks_context,
            "needs_reminders_context": decision.needs_reminders_context,
            "needs_summaries_context": decision.needs_summaries_context,
            "needs_tool_runs_context": decision.needs_tool_runs_context,
            "needs_care_context": decision.needs_care_context,
            "requested_scopes": list(decision.requested_scopes),
            "method": decision.method,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "matched_keywords": list(decision.matched_keywords),
        }

        if event_type is not None:
            context.setdefault("event_type", event_type)
        if source is not None:
            context.setdefault("source", source)

        if not decision.requested_scopes:
            return context

        if self.memory_store is None:
            return context

        for scope in decision.requested_scopes:
            self._inject_scope(context, scope)

        project_scopes = [
            scope
            for scope in decision.requested_scopes
            if scope in {
                "work",
                "notes",
                "tasks",
                "reminders",
                "summaries",
                "tool_runs",
                "care",
            }
        ]
        if project_scopes:
            self._inject_project_memory(context, project_scopes)

        return context

    def _inject_scope(self, context: dict, scope: str) -> None:
        try:
            if scope == "work":
                self._inject_work_context(context)
            elif scope == "notes":
                self._inject_notes_context(context)
            elif scope == "tasks":
                self._inject_tasks_context(context)
            elif scope == "reminders":
                self._inject_reminders_context(context)
            elif scope == "summaries":
                self._inject_summaries_context(context)
            elif scope in {"tool_runs", "care"}:
                return
        except Exception as exc:
            context.setdefault("context_errors", []).append({
                "scope": scope,
                "error": str(exc),
            })

    def _inject_work_context(self, context: dict) -> None:
        work_context: dict[str, Any] = {}
        get_summary = getattr(self.memory_store, "get_recent_work_summary", None)
        if callable(get_summary):
            work_context["recent_summary"] = get_summary(limit=self.work_limit)

        query_activities = getattr(self.memory_store, "query_recent_work_activities", None)
        if callable(query_activities):
            work_context["recent_activities"] = [
                {
                    "id": row.get("id"),
                    "timestamp_ms": row.get("timestamp_ms"),
                    "app_name": row.get("app_name"),
                    "window_title": self._preview(row.get("window_title")),
                    "activity_type": row.get("activity_type"),
                    "project_hint": row.get("project_hint"),
                    "duration_seconds": row.get("duration_seconds"),
                }
                for row in query_activities(limit=5)
            ]

        if work_context:
            context["work"] = work_context

    def _inject_notes_context(self, context: dict) -> None:
        notes_context: dict[str, Any] = {}
        get_summary = getattr(self.memory_store, "get_notes_summary", None)
        if callable(get_summary):
            notes_context["summary"] = get_summary(limit=self.work_limit)

        query_notes = getattr(self.memory_store, "query_recent_notes", None)
        if callable(query_notes):
            notes_context["recent_notes"] = [
                {
                    "id": row.get("id"),
                    "timestamp_ms": row.get("timestamp_ms"),
                    "content": self._preview(row.get("content")),
                    "tags": list(row.get("tags") or []),
                    "source": row.get("source"),
                    "project_hint": row.get("project_hint"),
                }
                for row in query_notes(limit=5)
            ]

        if notes_context:
            context["notes"] = notes_context

    def _inject_tasks_context(self, context: dict) -> None:
        tasks_context: dict[str, Any] = {}
        get_summary = getattr(self.memory_store, "get_tasks_summary", None)
        if callable(get_summary):
            tasks_context["summary"] = get_summary(limit=self.work_limit)

        query_tasks = getattr(self.memory_store, "query_tasks", None)
        if callable(query_tasks):
            try:
                task_rows = query_tasks(
                    limit=5,
                    status="pending",
                )
            except TypeError:
                task_rows = query_tasks(
                    limit=5,
                    include_done=False,
                )
            tasks_context["recent_tasks"] = [
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
                for row in task_rows
            ]

        if tasks_context:
            context["tasks"] = tasks_context

    def _inject_reminders_context(self, context: dict) -> None:
        reminders_context: dict[str, Any] = {}
        get_summary = getattr(self.memory_store, "get_reminders_summary", None)
        if callable(get_summary):
            reminders_context["summary"] = get_summary(limit=self.work_limit)

        query_reminders = getattr(self.memory_store, "query_reminders", None)
        if callable(query_reminders):
            try:
                reminder_rows = query_reminders(
                    limit=5,
                    status="pending",
                )
            except TypeError:
                reminder_rows = query_reminders(
                    limit=5,
                    include_fired=False,
                )
            reminders_context["recent_reminders"] = [
                {
                    "id": row.get("id"),
                    "due_at_ms": row.get("due_at_ms"),
                    "status": row.get("status"),
                    "message": self._preview(row.get("message")),
                    "project_hint": row.get("project_hint"),
                }
                for row in reminder_rows
            ]

        if reminders_context:
            context["reminders"] = reminders_context

    def _inject_summaries_context(self, context: dict) -> None:
        summaries_context: dict[str, Any] = {}
        get_overview = getattr(self.memory_store, "get_summary_overview", None)
        if callable(get_overview):
            summaries_context["overview"] = get_overview(limit=self.work_limit)

        query_summaries = getattr(self.memory_store, "query_recent_summaries", None)
        if callable(query_summaries):
            summaries_context["recent_summaries"] = [
                {
                    "summary_type": row.get("summary_type"),
                    "title": row.get("title"),
                    "date": row.get("date"),
                    "content_preview": self._preview(row.get("content")),
                }
                for row in query_summaries(limit=5)
            ]

        if summaries_context:
            context["summaries"] = summaries_context

    def _inject_project_memory(self, context: dict, scopes: list[str]) -> None:
        if self.project_memory is None:
            return
        scope_map = {
            "work": "work_activities",
            "notes": "notes",
            "tasks": "tasks",
            "reminders": "reminders",
            "summaries": "summaries",
            "tool_runs": "tool_runs",
            "care": "care_events",
        }
        selected_scope = scope_map[scopes[0]] if len(scopes) == 1 else None
        try:
            context["project_memory"] = self.project_memory.get_recent_project_context(
                limit=min(5, self.work_limit),
                scope=selected_scope,
            )
        except Exception as exc:
            context.setdefault("context_errors", []).append({
                "scope": "project_memory",
                "error": str(exc),
            })

    def build(self, trigger: dict) -> dict:
        payload = trigger.get("payload") if isinstance(trigger.get("payload"), dict) else {}
        text = trigger.get("text") or payload.get("text")
        return self.build_for_text(text, base_context=trigger)

    def close(self) -> None:
        return None

    @staticmethod
    def _preview(value: Any, limit: int = 160) -> str | None:
        if value is None:
            return None
        text = str(value)
        if len(text) <= limit:
            return text
        return f"{text[:limit - 3]}..."
