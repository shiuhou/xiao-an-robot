"""Local placeholder tools executed from OpenClaw tool calls."""

from __future__ import annotations

import time
from typing import Any


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
        metadata = {
            "work_summary": self._safe_memory_call("get_recent_work_summary"),
            "notes_summary": self._safe_memory_call("get_notes_summary"),
            "tool_run_summary": self._safe_memory_call("get_tool_run_summary"),
        }
        content = self._build_daily_summary_content(date, metadata)
        title = arguments.get("title") or f"Daily Summary {date}"
        try:
            summary_result = self.memory_store.insert_summary(
                summary_type="daily",
                title=title,
                content=content,
                date=date,
                source="tool_call",
                project_hint=project_hint,
                project_id=arguments.get("project_id"),
                metadata=metadata,
            )
        except Exception as exc:
            return {"ok": False, "name": "summary.daily", "error": str(exc)}

        return {
            "ok": True,
            "name": "summary.daily",
            "result": {
                "date": date,
                "status": "generated",
                "persisted": True,
                "summary_result": summary_result,
                "content": content,
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

    @staticmethod
    def _build_daily_summary_content(date: str, metadata: dict) -> str:
        work_count = (metadata.get("work_summary") or {}).get("count", 0)
        note_count = (metadata.get("notes_summary") or {}).get("count", 0)
        tool_count = (metadata.get("tool_run_summary") or {}).get("count", 0)
        return (
            f"Daily summary for {date}\n"
            f"- Work activities: {work_count}\n"
            f"- Notes: {note_count}\n"
            f"- Tool runs: {tool_count}"
        )
