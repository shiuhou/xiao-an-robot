"""Rule-based daily summary builder over Xiao An unified memory."""

from __future__ import annotations

from datetime import date as date_type
from typing import Any


class DailySummaryBuilder:
    """Build a structured daily summary without calling an LLM."""

    def __init__(self, memory_store: Any, default_limit: int = 20):
        self.memory_store = memory_store
        self.default_limit = int(default_limit)

    def build(
        self,
        date: str | None = None,
        project_hint: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        active_date = self._normalize_date(date)
        active_limit = int(limit or self.default_limit)
        errors: list[dict[str, str]] = []

        work_summary = self._safe_call(errors, "get_recent_work_summary", limit=active_limit) or {}
        work_activities = self._safe_call(errors, "query_recent_work_activities", limit=active_limit) or []
        notes_summary = self._safe_call(errors, "get_notes_summary", limit=active_limit) or {}
        notes = self._safe_call(
            errors,
            "query_recent_notes",
            limit=active_limit,
            project_hint=project_hint,
        ) or []
        tasks_summary = self._safe_call(errors, "get_tasks_summary", limit=active_limit) or {}
        tasks = self._safe_call(
            errors,
            "query_tasks",
            limit=active_limit,
            include_done=True,
            project_hint=project_hint,
        ) or []
        reminders_summary = self._safe_call(errors, "get_reminders_summary", limit=active_limit) or {}
        reminders = self._safe_call(
            errors,
            "query_reminders",
            limit=active_limit,
            include_fired=True,
        ) or []
        tool_summary = self._safe_call(errors, "get_tool_run_summary", limit=active_limit) or {}
        tool_runs = self._safe_call(errors, "query_recent_tool_runs", limit=active_limit) or []
        emotion_summary = self._safe_call(errors, "get_emotion_summary", hours=24) or {}

        counts = {
            "work_activities": work_summary.get("count", len(work_activities) if isinstance(work_activities, list) else 0),
            "notes": notes_summary.get("count", len(notes) if isinstance(notes, list) else 0),
            "tasks": tasks_summary.get("count", len(tasks) if isinstance(tasks, list) else 0),
            "pending_tasks": tasks_summary.get("pending_count", self._count_by_status(tasks, "pending")),
            "done_tasks": tasks_summary.get("done_count", self._count_by_status(tasks, "done")),
            "cancelled_tasks": tasks_summary.get("cancelled_count", self._count_by_status(tasks, "cancelled")),
            "reminders": reminders_summary.get("count", len(reminders) if isinstance(reminders, list) else 0),
            "pending_reminders": reminders_summary.get("pending_count", self._count_by_status(reminders, "pending")),
            "fired_reminders": reminders_summary.get("fired_count", self._count_by_status(reminders, "fired")),
            "tool_runs": tool_summary.get("count", len(tool_runs) if isinstance(tool_runs, list) else 0),
            "emotions": emotion_summary.get("count", 0),
        }
        sections = [
            "今日概览",
            "工作活动",
            "笔记",
            "任务",
            "提醒",
            "工具调用",
            "情绪与疲劳",
            "下一步建议",
        ]
        metadata = {
            "date": active_date,
            "input_date": date,
            "project_hint": project_hint,
            "sections": sections,
            "counts": counts,
        }
        if errors:
            metadata["errors"] = errors

        title = f"小安日报 - {active_date}"
        content = self._build_content(
            title=title,
            counts=counts,
            work_summary=work_summary,
            notes=notes,
            tasks=tasks,
            reminders=reminders,
            tool_summary=tool_summary,
            emotion_summary=emotion_summary,
        )
        return {
            "summary_type": "daily",
            "title": title,
            "date": active_date,
            "content": content,
            "metadata": metadata,
        }

    def _safe_call(self, errors: list[dict[str, str]], method_name: str, **kwargs) -> Any:
        method = getattr(self.memory_store, method_name, None)
        if not callable(method):
            return None
        try:
            return method(**kwargs)
        except Exception as exc:
            errors.append({"scope": method_name, "error": str(exc)})
            return None

    @staticmethod
    def _normalize_date(date: str | None) -> str:
        if date is None:
            return date_type.today().isoformat()
        value = str(date).strip()
        if not value or value in {"today", "今天"}:
            return date_type.today().isoformat()
        return value

    def _build_content(
        self,
        title: str,
        counts: dict[str, int],
        work_summary: dict[str, Any],
        notes: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        reminders: list[dict[str, Any]],
        tool_summary: dict[str, Any],
        emotion_summary: dict[str, Any],
    ) -> str:
        lines = [
            title,
            "",
            "一、今日概览",
            f"- 工作活动记录：{counts['work_activities']} 条",
            f"- 笔记：{counts['notes']} 条",
            f"- 任务：待办 {counts['pending_tasks']} 个，完成 {counts['done_tasks']} 个",
            f"- 提醒：待触发 {counts['pending_reminders']} 个，已触发 {counts['fired_reminders']} 个",
            f"- 工具调用：{counts['tool_runs']} 次",
            "",
            "二、工作活动",
        ]
        lines.extend(self._work_lines(work_summary))
        lines.extend(["", "三、笔记"])
        lines.extend(self._note_lines(notes))
        lines.extend(["", "四、任务"])
        lines.extend(self._task_lines(tasks))
        lines.extend(["", "五、提醒"])
        lines.extend(self._reminder_lines(reminders))
        lines.extend(["", "六、工具调用"])
        lines.extend(self._tool_lines(tool_summary))
        lines.extend(["", "七、情绪与疲劳"])
        lines.extend(self._emotion_lines(emotion_summary))
        lines.extend(["", "八、下一步建议"])
        lines.extend(self._suggestion_lines(counts, work_summary))
        return "\n".join(lines)

    def _work_lines(self, work_summary: dict[str, Any]) -> list[str]:
        if not work_summary or not work_summary.get("count", 0):
            return ["- 暂无工作活动记录"]
        return [
            f"- 主要活动：{work_summary.get('top_activity_type') or work_summary.get('latest_activity_type') or '暂无'}",
            f"- 主要应用：{work_summary.get('top_app_name') or work_summary.get('latest_app_name') or '暂无'}",
            f"- 关联项目：{work_summary.get('latest_project_hint') or '暂无'}",
        ]

    def _note_lines(self, notes: list[dict[str, Any]]) -> list[str]:
        recent = [str(note.get("content", "")).strip() for note in notes[:3] if note.get("content")]
        if not recent:
            return ["- 暂无笔记记录"]
        return [f"- {item}" for item in recent]

    def _task_lines(self, tasks: list[dict[str, Any]]) -> list[str]:
        pending = [task for task in tasks if task.get("status") == "pending"]
        done = [task for task in tasks if task.get("status") == "done"]
        lines: list[str] = []
        lines.extend(self._labelled_items("待办", pending, "title"))
        lines.extend(self._labelled_items("已完成", done, "title"))
        return lines or ["- 暂无任务记录"]

    def _reminder_lines(self, reminders: list[dict[str, Any]]) -> list[str]:
        pending = [item for item in reminders if item.get("status") == "pending"]
        fired = [item for item in reminders if item.get("status") == "fired"]
        lines: list[str] = []
        lines.extend(self._labelled_items("待触发", pending, "message"))
        lines.extend(self._labelled_items("已触发", fired, "message"))
        return lines or ["- 暂无提醒记录"]

    def _tool_lines(self, tool_summary: dict[str, Any]) -> list[str]:
        tool_count = tool_summary.get("tool_count") or {}
        if not tool_count:
            return ["- 暂无工具调用记录"]
        return [f"- {name}: {count}" for name, count in list(tool_count.items())[:5]]

    def _emotion_lines(self, emotion_summary: dict[str, Any]) -> list[str]:
        if not emotion_summary or not emotion_summary.get("count", 0):
            return ["- 最近暂无明显异常记录"]
        top_emotion = emotion_summary.get("top_emotion") or "unknown"
        fatigue = emotion_summary.get("avg_fatigue_score", 0.0)
        return [f"- 主要情绪：{top_emotion}", f"- 平均疲劳分：{fatigue:.2f}"]

    def _suggestion_lines(self, counts: dict[str, int], work_summary: dict[str, Any]) -> list[str]:
        lines = []
        if counts.get("pending_tasks", 0) > 0:
            lines.append("- 优先处理未完成任务")
        if work_summary.get("latest_project_hint"):
            lines.append("- 根据最近工作活动继续推进项目")
        if not lines:
            lines.append("- 今天记录较少，可以先补充关键事项")
        return lines

    @staticmethod
    def _labelled_items(label: str, rows: list[dict[str, Any]], key: str) -> list[str]:
        values = [str(row.get(key, "")).strip() for row in rows[:3] if row.get(key)]
        if not values:
            return [f"- {label}：暂无"]
        return [f"- {label}：{value}" for value in values]

    @staticmethod
    def _count_by_status(rows: list[dict[str, Any]], status: str) -> int:
        return sum(1 for row in rows if row.get("status") == status)
