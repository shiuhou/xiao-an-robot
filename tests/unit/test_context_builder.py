"""Unit tests for ContextBuilder memory-scope injection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.context_builder import ContextBuilder
from agent.core.memory import XiaoAnMemoryStore
from agent.core.project_memory import ProjectMemoryService


WORK_SUMMARY = {
    "count": 3,
    "latest_activity_type": "coding",
    "latest_app_name": "VS Code",
    "latest_project_hint": "xiao-an-robot",
    "top_activity_type": "coding",
    "top_app_name": "VS Code",
    "activity_type_count": {"coding": 3},
    "app_count": {"VS Code": 3},
    "project_hint_count": {"xiao-an-robot": 3},
}


class FakeContextMemory:
    def get_recent_work_summary(self, limit: int = 20) -> dict:
        return dict(WORK_SUMMARY)

    def query_recent_work_activities(self, limit: int = 5) -> list[dict]:
        return [{
            "app_name": "VS Code",
            "activity_type": "coding",
            "project_hint": "xiao-an-robot",
        }]

    def get_notes_summary(self, limit: int = 20) -> dict:
        return {"count": 1, "latest_content": "明天下午交报告"}

    def query_recent_notes(self, limit: int = 5) -> list[dict]:
        return [{"content": "明天下午交报告", "tags": ["work_context"]}]

    def get_tasks_summary(self, limit: int = 20) -> dict:
        return {"count": 2, "pending_count": 1, "done_count": 1}

    def query_tasks(self, limit: int = 10, include_done: bool = False) -> list[dict]:
        return [
            {"title": "完成 Step 24", "status": "pending"},
            {"title": "完成 Step 23.5", "status": "done"},
        ]

    def get_reminders_summary(self, limit: int = 20) -> dict:
        return {"count": 1, "pending_count": 1, "fired_count": 0}

    def query_reminders(self, limit: int = 10, include_fired: bool = False) -> list[dict]:
        return [{"message": "休息一下", "status": "pending"}]

    def get_summary_overview(self, limit: int = 20) -> dict:
        return {"count": 1, "latest_summary_type": "daily", "latest_title": "小安日报"}

    def query_recent_summaries(self, limit: int = 5) -> list[dict]:
        return [{"summary_type": "daily", "title": "小安日报"}]


class RaisingNotesMemory(FakeContextMemory):
    def get_notes_summary(self, limit: int = 20) -> dict:
        raise RuntimeError("notes memory unavailable")


class ContextBuilderTest(unittest.TestCase):
    def test_normal_text_does_not_add_memory_scopes(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("今天天气怎么样")

        for scope in ("work", "notes", "tasks", "reminders", "summaries"):
            self.assertNotIn(scope, context)
        self.assertFalse(context["context_policy"]["needs_work_context"])
        self.assertEqual(context["context_policy"]["requested_scopes"], [])
        self.assertEqual(context["context_policy"]["method"], "keyword_heuristic")
        self.assertEqual(context["context_policy"]["reason"], "no_context_needed")

    def test_work_text_adds_recent_summary(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("我刚刚在做什么")

        self.assertEqual(context["context_policy"]["requested_scopes"], ["work"])
        self.assertEqual(context["work"]["recent_summary"]["latest_activity_type"], "coding")
        self.assertEqual(context["work"]["recent_activities"][0]["app_name"], "VS Code")

    def test_note_question_injects_notes_only(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("我刚刚记了什么")

        self.assertEqual(context["context_policy"]["requested_scopes"], ["notes"])
        self.assertIn("notes", context)
        self.assertNotIn("work", context)
        self.assertNotIn("tasks", context)
        self.assertNotIn("reminders", context)
        self.assertEqual(context["notes"]["recent_notes"][0]["content"], "明天下午交报告")

    def test_task_question_injects_tasks(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("我今天还有什么任务")

        self.assertEqual(context["context_policy"]["requested_scopes"], ["tasks"])
        self.assertEqual(context["tasks"]["recent_tasks"][0]["title"], "完成 Step 24")

    def test_reminder_question_injects_reminders(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("刚才设了什么提醒")

        self.assertEqual(context["context_policy"]["requested_scopes"], ["reminders"])
        self.assertEqual(context["reminders"]["recent_reminders"][0]["message"], "休息一下")
        self.assertNotIn("work", context)

    def test_summary_question_injects_all_memory_scopes(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("总结一下今天进展")

        self.assertEqual(context["context_policy"]["requested_scopes"], [
            "work",
            "notes",
            "tasks",
            "reminders",
            "summaries",
            "tool_runs",
            "care",
        ])
        for scope in ("work", "notes", "tasks", "reminders", "summaries"):
            self.assertIn(scope, context)

    def test_build_for_text_preserves_base_payload(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())
        payload = {"text": "我刚刚记了什么", "session_id": "s1"}

        context = builder.build_for_text(
            "我刚刚记了什么",
            base_context={"payload": payload},
        )

        self.assertEqual(context["payload"], payload)
        self.assertIn("notes", context)

    def test_scope_error_adds_context_errors_and_keeps_other_scopes(self) -> None:
        builder = ContextBuilder(memory_store=RaisingNotesMemory())

        context = builder.build_for_text("总结一下今天进展")

        self.assertEqual(context["context_errors"][0]["scope"], "notes")
        self.assertIn("notes memory unavailable", context["context_errors"][0]["error"])
        self.assertIn("work", context)
        self.assertIn("tasks", context)
        self.assertIn("reminders", context)
        self.assertIn("summaries", context)
        self.assertNotIn("notes", context)

    def test_matched_keywords_enter_context_policy(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("继续刚才的项目")

        self.assertEqual(context["context_policy"]["matched_keywords"], [
            "刚才",
            "继续",
            "继续刚才",
            "项目",
        ])
        self.assertEqual(context["context_policy"]["method"], "keyword_heuristic")

    def test_build_compatibility_uses_trigger_text(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build({
            "payload": {"text": "今天天气怎么样"},
            "text": "我刚刚记了什么",
        })

        self.assertIn("notes", context)
        self.assertEqual(context["text"], "我刚刚记了什么")

    def test_build_compatibility_uses_payload_text(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build({"payload": {"text": "我今天还有什么任务"}})

        self.assertIn("tasks", context)

    def test_none_memory_store_work_text_does_not_crash(self) -> None:
        builder = ContextBuilder(memory_store=None)

        context = builder.build_for_text("总结一下今天进展")

        self.assertEqual(context["context_policy"]["requested_scopes"], [
            "work",
            "notes",
            "tasks",
            "reminders",
            "summaries",
            "tool_runs",
            "care",
        ])
        for scope in ("work", "notes", "tasks", "reminders", "summaries"):
            self.assertNotIn(scope, context)

    def test_real_project_memory_is_compact_and_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "context_project_memory.db")
            with XiaoAnMemoryStore(db_path) as store:
                service = ProjectMemoryService(memory_store=store)
                service.record_note("remember the API decision")
                service.record_work_activity(
                    "editing context builder",
                    payload={"app_name": "VS Code", "activity_type": "coding"},
                )
                long_summary = "daily details " * 100
                service.record_summary(
                    long_summary,
                    payload={"title": "Daily progress", "date": "2026-06-20"},
                )
                service.record_tool_run("note.add", result={"large": "x" * 1000})
                for event_type in (
                    "companion.request",
                    "emotion.intervention",
                    "robot.care_action",
                ):
                    store.insert_event(
                        event_type=event_type,
                        source="brain",
                        text=event_type,
                        payload={"payload_json": "must not leak", "large": "y" * 1000},
                    )
                builder = ContextBuilder(memory_store=store)

                notes_context = builder.build_for_text("我刚才让你记了什么？")
                work_context = builder.build_for_text("我刚才在做什么？")
                summary_context = builder.build_for_text("总结一下今天进展")
                tools_context = builder.build_for_text("今天有哪些工具调用？")
                care_context = builder.build_for_text("小安刚才有没有关心过我？")

                self.assertEqual(
                    notes_context["project_memory"]["recent_notes"][0]["content"],
                    "remember the API decision",
                )
                self.assertEqual(
                    work_context["project_memory"]["recent_work_activities"][0]["app_name"],
                    "VS Code",
                )
                summary_row = summary_context["project_memory"]["recent_summaries"][0]
                self.assertEqual(summary_row["title"], "Daily progress")
                self.assertLessEqual(len(summary_row["content_preview"]), 160)
                self.assertNotEqual(summary_row["content_preview"], long_summary)
                self.assertEqual(
                    tools_context["project_memory"]["recent_tool_runs"][0]["tool_name"],
                    "note.add",
                )
                self.assertNotIn(
                    "result",
                    tools_context["project_memory"]["recent_tool_runs"][0],
                )
                care_types = {
                    event["event_type"]
                    for event in care_context["project_memory"]["recent_care_events"]
                }
                self.assertEqual(care_types, {
                    "companion.request",
                    "emotion.intervention",
                    "robot.care_action",
                })
                self.assertNotIn(
                    "payload_json",
                    repr(summary_context),
                )

    def test_casual_text_does_not_inject_project_memory(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        for text in ("你好小安", "讲个笑话", "你是谁", "今天天气怎么样"):
            with self.subTest(text=text):
                context = builder.build_for_text(text)
                self.assertNotIn("project_memory", context)

    def test_real_task_and_reminder_questions_inject_compact_project_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "task_reminder_context.db")
            with XiaoAnMemoryStore(db_path) as store:
                for index in range(7):
                    store.insert_task(title=f"pending task {index}")
                    store.insert_reminder(
                        message=f"pending reminder {index}",
                        delay_seconds=60,
                        metadata={"large": "x" * 1000},
                    )
                builder = ContextBuilder(memory_store=store)

                task_context = builder.build_for_text("我还有哪些任务？")
                reminder_context = builder.build_for_text("明天有什么提醒？")

                task_memory = task_context["project_memory"]
                reminder_memory = reminder_context["project_memory"]
                self.assertEqual(task_memory["scope"], "tasks")
                self.assertEqual(len(task_memory["recent_tasks"]), 5)
                self.assertEqual(task_memory["tasks_summary"]["pending_count"], 7)
                self.assertEqual(reminder_memory["scope"], "reminders")
                self.assertEqual(len(reminder_memory["recent_reminders"]), 5)
                self.assertEqual(
                    reminder_memory["reminders_summary"]["pending_count"],
                    7,
                )
                self.assertNotIn("metadata_json", repr(reminder_context))
                self.assertNotIn("x" * 1000, repr(reminder_context))


if __name__ == "__main__":
    unittest.main()
