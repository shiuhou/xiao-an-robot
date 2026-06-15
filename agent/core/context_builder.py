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
            "reason": decision.reason,
            "matched_keywords": list(decision.matched_keywords),
        }

        if event_type is not None:
            context.setdefault("event_type", event_type)
        if source is not None:
            context.setdefault("source", source)

        if not decision.needs_work_context:
            return context

        if self.memory_store is None:
            return context

        try:
            work_context: dict[str, Any] = {}
            get_summary = getattr(self.memory_store, "get_recent_work_summary", None)
            if callable(get_summary):
                work_context["recent_summary"] = get_summary(limit=self.work_limit)

            query_activities = getattr(self.memory_store, "query_recent_work_activities", None)
            if callable(query_activities):
                work_context["recent_activities"] = query_activities(limit=5)

            if work_context:
                context["work"] = work_context
        except Exception as exc:
            context.setdefault("context_errors", []).append({
                "scope": "work",
                "error": str(exc),
            })

        return context

    def build(self, trigger: dict) -> dict:
        payload = trigger.get("payload") if isinstance(trigger.get("payload"), dict) else {}
        text = trigger.get("text") or payload.get("text")
        return self.build_for_text(text, base_context=trigger)

    def close(self) -> None:
        return None
