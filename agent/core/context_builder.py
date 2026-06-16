"""Assemble optional Xiao An context for OpenClaw events."""

from __future__ import annotations

from typing import Any

from agent.core.context_policy import ContextInjectionPolicy


class ContextBuilder:
    """Build event context without deciding how OpenClaw should respond."""

    def __init__(
        self,
        memory_store: Any | None = None,
        policy: ContextInjectionPolicy | None = None,
        work_limit: int = 20,
    ):
        self.memory_store = memory_store
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
            work_context["recent_activities"] = query_activities(limit=5)

        if work_context:
            context["work"] = work_context

    def _inject_notes_context(self, context: dict) -> None:
        notes_context: dict[str, Any] = {}
        get_summary = getattr(self.memory_store, "get_notes_summary", None)
        if callable(get_summary):
            notes_context["summary"] = get_summary(limit=self.work_limit)

        query_notes = getattr(self.memory_store, "query_recent_notes", None)
        if callable(query_notes):
            notes_context["recent_notes"] = query_notes(limit=5)

        if notes_context:
            context["notes"] = notes_context

    def _inject_tasks_context(self, context: dict) -> None:
        tasks_context: dict[str, Any] = {}
        get_summary = getattr(self.memory_store, "get_tasks_summary", None)
        if callable(get_summary):
            tasks_context["summary"] = get_summary(limit=self.work_limit)

        query_tasks = getattr(self.memory_store, "query_tasks", None)
        if callable(query_tasks):
            tasks_context["recent_tasks"] = query_tasks(limit=10, include_done=True)

        if tasks_context:
            context["tasks"] = tasks_context

    def _inject_reminders_context(self, context: dict) -> None:
        reminders_context: dict[str, Any] = {}
        get_summary = getattr(self.memory_store, "get_reminders_summary", None)
        if callable(get_summary):
            reminders_context["summary"] = get_summary(limit=self.work_limit)

        query_reminders = getattr(self.memory_store, "query_reminders", None)
        if callable(query_reminders):
            reminders_context["recent_reminders"] = query_reminders(limit=10, include_fired=True)

        if reminders_context:
            context["reminders"] = reminders_context

    def _inject_summaries_context(self, context: dict) -> None:
        summaries_context: dict[str, Any] = {}
        get_overview = getattr(self.memory_store, "get_summary_overview", None)
        if callable(get_overview):
            summaries_context["overview"] = get_overview(limit=self.work_limit)

        query_summaries = getattr(self.memory_store, "query_recent_summaries", None)
        if callable(query_summaries):
            summaries_context["recent_summaries"] = query_summaries(limit=5)

        if summaries_context:
            context["summaries"] = summaries_context

    def build(self, trigger: dict) -> dict:
        payload = trigger.get("payload") if isinstance(trigger.get("payload"), dict) else {}
        text = trigger.get("text") or payload.get("text")
        return self.build_for_text(text, base_context=trigger)

    def close(self) -> None:
        return None
