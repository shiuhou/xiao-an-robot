"""Unit tests for ContextBuilder memory-scope injection."""

from __future__ import annotations

import unittest

from agent.core.context_builder import ContextBuilder


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
        ])
        for scope in ("work", "notes", "tasks", "reminders", "summaries"):
            self.assertNotIn(scope, context)


if __name__ == "__main__":
    unittest.main()
