"""Local placeholder tools executed from OpenClaw tool calls."""

from __future__ import annotations

import time
from typing import Any

from agent.core.daily_summary_builder import DailySummaryBuilder


class LocalToolRegistry:
    """Small local tool placeholder registry with no side effects."""

    def __init__(self, memory_store: Any | None = None):
        self.memory_store = memory_store

    def execute(self, name: str, arguments: dict | None = None) -> dict:
        active_arguments = arguments if isinstance(arguments, dict) else {}

        if name == "note.add":
            return self._execute_note_add(active_arguments)

        if name == "work_context.record":
            return self._execute_work_context_record(active_arguments)

        if name == "summary.daily":
            return self._execute_summary_daily(active_arguments)

        if name == "reminder.add":
            return self._execute_reminder_add(active_arguments)

        if name == "reminder.query":
            return self._execute_reminder_query(active_arguments)

        if name == "reminder.cancel":
            return self._execute_reminder_cancel(active_arguments)

        if name == "task.add":
            return self._execute_task_add(active_arguments)

        if name == "task.query":
            return self._execute_task_query(active_arguments)

        if name == "task.complete":
            return self._execute_task_complete(active_arguments)

        if name == "task.cancel":
            return self._execute_task_cancel(active_arguments)

        return {
            "ok": False,
            "name": name,
            "error": "unsupported local tool",
        }

    def _execute_note_add(self, arguments: dict) -> dict:
        tags = self._normalize_tags(arguments.get("tags", []))
        content = arguments.get("content", "")
        if not self._has_memory_method("insert_note"):
            return {
                "ok": True,
                "name": "note.add",
                "result": {
                    "content": content,
                    "tags": tags,
                    "persisted": False,
                },
            }
        if not content:
            return {"ok": False, "name": "note.add", "error": "missing_content"}

        try:
            note_result = self.memory_store.insert_note(
                content=content,
                tags=tags,
                source="tool_call",
                project_hint=arguments.get("project_hint"),
                project_id=arguments.get("project_id"),
            )
        except Exception as exc:
            return {"ok": False, "name": "note.add", "error": str(exc)}

        return {
            "ok": True,
            "name": "note.add",
            "result": {
                "content": content,
                "tags": tags,
                "persisted": True,
                "note_result": note_result,
            },
        }

    def _execute_work_context_record(self, arguments: dict) -> dict:
        content = arguments.get("content") or arguments.get("text", "")
        tags = self._merge_tags(["work_context"], self._normalize_tags(arguments.get("tags", [])))
        if not self._has_memory_method("insert_note"):
            return {
                "ok": True,
                "name": "work_context.record",
                "result": {
                    "content": content,
                    "source": arguments.get("source", "openclaw"),
                    "tags": tags,
                    "persisted": False,
                },
            }
        if not content:
            return {"ok": False, "name": "work_context.record", "error": "missing_content"}

        try:
            note_result = self.memory_store.insert_note(
                content=content,
                tags=tags,
                source="tool_call",
                project_hint=arguments.get("project_hint"),
                project_id=arguments.get("project_id"),
            )
        except Exception as exc:
            return {"ok": False, "name": "work_context.record", "error": str(exc)}

        return {
            "ok": True,
            "name": "work_context.record",
            "result": {
                "content": content,
                "source": arguments.get("source", "openclaw"),
                "tags": tags,
                "persisted": True,
                "note_result": note_result,
            },
        }

    def _execute_summary_daily(self, arguments: dict) -> dict:
        date = arguments.get("date") or time.strftime("%Y-%m-%d")
        if not self._has_memory_method("insert_summary"):
            return {
                "ok": True,
                "name": "summary.daily",
                "result": {
                    "date": date,
                    "status": "placeholder",
                    "persisted": False,
                },
            }

        project_hint = arguments.get("project_hint")
        summary = DailySummaryBuilder(self.memory_store).build(
            date=arguments.get("date"),
            project_hint=project_hint,
        )
        try:
            summary_result = self.memory_store.insert_summary(
                summary_type="daily",
                title=summary["title"],
                content=summary["content"],
                date=summary["date"],
                source="tool_call",
                project_hint=project_hint,
                project_id=arguments.get("project_id"),
                metadata=summary["metadata"],
            )
        except Exception as exc:
            return {"ok": False, "name": "summary.daily", "error": str(exc)}

        return {
            "ok": True,
            "name": "summary.daily",
            "result": {
                "date": summary["date"],
                "status": "generated",
                "persisted": True,
                "summary_result": summary_result,
                "summary": summary,
                "content": summary["content"],
            },
        }

    def _execute_reminder_add(self, arguments: dict) -> dict:
        message = arguments.get("message") or arguments.get("content") or arguments.get("text") or ""
        delay_seconds = arguments.get("delay_seconds")
        due_at_ms = arguments.get("due_at_ms")
        result = {
            "message": message,
            "due_at_ms": due_at_ms,
            "delay_seconds": delay_seconds,
            "persisted": False,
        }
        if not self._has_memory_method("insert_reminder"):
            return {
                "ok": True,
                "name": "reminder.add",
                "result": result,
            }
        if not message:
            return {"ok": False, "name": "reminder.add", "error": "missing_message"}

        try:
            reminder_result = self.memory_store.insert_reminder(
                message=message,
                due_at_ms=due_at_ms,
                delay_seconds=delay_seconds,
                source="tool_call",
                project_hint=arguments.get("project_hint"),
                metadata=arguments.get("metadata") if isinstance(arguments.get("metadata"), dict) else None,
            )
        except Exception as exc:
            return {"ok": False, "name": "reminder.add", "error": str(exc)}

        result.update({
            "persisted": True,
            "reminder_result": reminder_result,
        })
        return {
            "ok": True,
            "name": "reminder.add",
            "result": result,
        }

    def _execute_reminder_query(self, arguments: dict) -> dict:
        limit = int(arguments.get("limit", 20) or 20)
        status = arguments.get("status")
        include_fired = bool(arguments.get("include_fired", False))
        if not self._has_memory_method("query_reminders"):
            return {
                "ok": True,
                "name": "reminder.query",
                "reminders": [],
                "count": 0,
            }

        try:
            reminders = self.memory_store.query_reminders(
                limit=limit,
                status=status,
                include_fired=include_fired,
            )
        except Exception as exc:
            return {"ok": False, "name": "reminder.query", "error": str(exc)}

        return {
            "ok": True,
            "name": "reminder.query",
            "reminders": reminders,
            "count": len(reminders),
        }

    def _execute_reminder_cancel(self, arguments: dict) -> dict:
        reminder_id = arguments.get("reminder_id")
        message_contains = (
            arguments.get("message_contains")
            or arguments.get("content")
            or arguments.get("text")
            or arguments.get("message")
        )
        if not self._has_memory_method("cancel_reminder"):
            return {
                "ok": True,
                "name": "reminder.cancel",
                "result": {
                    "persisted": False,
                    "reminder_id": reminder_id,
                    "message_contains": message_contains,
                },
            }

        try:
            cancel_result = self.memory_store.cancel_reminder(
                reminder_id=reminder_id,
                message_contains=message_contains,
                source="tool_call",
            )
        except Exception as exc:
            return {"ok": False, "name": "reminder.cancel", "error": str(exc)}

        if not cancel_result.get("ok", False):
            return {
                "ok": False,
                "name": "reminder.cancel",
                "reason": cancel_result.get("reason", "not_found"),
                "result": cancel_result,
            }
        return {
            "ok": True,
            "name": "reminder.cancel",
            "result": {
                "persisted": True,
                "cancel_result": cancel_result,
            },
        }

    def _execute_task_add(self, arguments: dict) -> dict:
        title = arguments.get("title") or arguments.get("content") or arguments.get("text") or ""
        result = {
            "title": title,
            "description": arguments.get("description"),
            "due_at_ms": arguments.get("due_at_ms"),
            "due_text": arguments.get("due_text"),
            "priority": arguments.get("priority", "normal"),
            "project_hint": arguments.get("project_hint"),
            "persisted": False,
        }
        if not self._has_memory_method("insert_task"):
            return {
                "ok": True,
                "name": "task.add",
                "result": result,
            }
        if not title:
            return {"ok": False, "name": "task.add", "error": "missing_title"}

        try:
            task_result = self.memory_store.insert_task(
                title=title,
                description=arguments.get("description"),
                due_at_ms=arguments.get("due_at_ms"),
                due_text=arguments.get("due_text"),
                priority=arguments.get("priority", "normal"),
                source="tool_call",
                project_hint=arguments.get("project_hint"),
                project_id=arguments.get("project_id"),
                metadata=arguments.get("metadata") if isinstance(arguments.get("metadata"), dict) else None,
            )
        except Exception as exc:
            return {"ok": False, "name": "task.add", "error": str(exc)}

        result.update({
            "persisted": True,
            "task_result": task_result,
        })
        return {
            "ok": True,
            "name": "task.add",
            "result": result,
        }

    def _execute_task_query(self, arguments: dict) -> dict:
        limit = int(arguments.get("limit", 20) or 20)
        status = arguments.get("status")
        project_hint = arguments.get("project_hint")
        include_done = bool(arguments.get("include_done", False))
        if not self._has_memory_method("query_tasks"):
            return {
                "ok": True,
                "name": "task.query",
                "persisted": False,
                "tasks": [],
                "count": 0,
            }

        try:
            tasks = self.memory_store.query_tasks(
                limit=limit,
                status=status,
                project_hint=project_hint,
                include_done=include_done,
            )
        except Exception as exc:
            return {"ok": False, "name": "task.query", "error": str(exc)}

        return {
            "ok": True,
            "name": "task.query",
            "tasks": tasks,
            "count": len(tasks),
        }

    def _execute_task_complete(self, arguments: dict) -> dict:
        return self._execute_task_status_change(
            name="task.complete",
            method_name="complete_task",
            arguments=arguments,
        )

    def _execute_task_cancel(self, arguments: dict) -> dict:
        return self._execute_task_status_change(
            name="task.cancel",
            method_name="cancel_task",
            arguments=arguments,
        )

    def _execute_task_status_change(self, name: str, method_name: str, arguments: dict) -> dict:
        task_id = arguments.get("task_id")
        title_contains = (
            arguments.get("title_contains")
            or arguments.get("content")
            or arguments.get("text")
            or arguments.get("title")
        )
        if not self._has_memory_method(method_name):
            return {
                "ok": True,
                "name": name,
                "result": {
                    "persisted": False,
                    "task_id": task_id,
                    "title_contains": title_contains,
                },
            }

        try:
            task_result = getattr(self.memory_store, method_name)(
                task_id=task_id,
                title_contains=title_contains,
                source="tool_call",
            )
        except Exception as exc:
            return {"ok": False, "name": name, "error": str(exc)}

        if not task_result.get("ok", False):
            return {
                "ok": False,
                "name": name,
                "reason": task_result.get("reason", "not_found"),
                "result": task_result,
            }
        return {
            "ok": True,
            "name": name,
            "result": {
                "persisted": True,
                "task_result": task_result,
            },
        }

    def _has_memory_method(self, method_name: str) -> bool:
        return self.memory_store is not None and callable(getattr(self.memory_store, method_name, None))

    def _safe_memory_call(self, method_name: str) -> Any:
        if not self._has_memory_method(method_name):
            return None
        try:
            return getattr(self.memory_store, method_name)()
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _normalize_tags(tags: Any) -> list[str]:
        if not isinstance(tags, list):
            return []
        return [str(tag) for tag in tags if str(tag)]

    @staticmethod
    def _merge_tags(default_tags: list[str], extra_tags: list[str]) -> list[str]:
        merged: list[str] = []
        for tag in default_tags + extra_tags:
            if tag not in merged:
                merged.append(tag)
        return merged
