"""Local placeholder tools executed from OpenClaw tool calls."""

from __future__ import annotations

from typing import Any


class LocalToolRegistry:
    """Small local tool placeholder registry with no side effects."""

    def execute(self, name: str, arguments: dict | None = None) -> dict:
        active_arguments = arguments if isinstance(arguments, dict) else {}

        if name == "note.add":
            tags = active_arguments.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            return {
                "ok": True,
                "name": "note.add",
                "result": {
                    "content": active_arguments.get("content", ""),
                    "tags": tags,
                },
            }

        if name == "work_context.record":
            return {
                "ok": True,
                "name": "work_context.record",
                "result": {
                    "content": active_arguments.get("content", ""),
                    "source": active_arguments.get("source", "openclaw"),
                },
            }

        if name == "summary.daily":
            return {
                "ok": True,
                "name": "summary.daily",
                "result": {
                    "date": active_arguments.get("date", ""),
                    "status": "placeholder",
                },
            }

        return {
            "ok": False,
            "name": name,
            "error": "unsupported local tool",
        }
