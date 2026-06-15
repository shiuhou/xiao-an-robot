"""Unit tests for ContextBuilder work-context injection."""

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


class RaisingContextMemory:
    def get_recent_work_summary(self, limit: int = 20) -> dict:
        raise RuntimeError("work memory unavailable")


class ContextBuilderTest(unittest.TestCase):
    def test_normal_text_does_not_add_work(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("今天天气怎么样")

        self.assertNotIn("work", context)
        self.assertFalse(context["context_policy"]["needs_work_context"])
        self.assertEqual(context["context_policy"]["reason"], "no_context_needed")

    def test_work_text_adds_recent_summary(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("我刚刚在做什么")

        self.assertTrue(context["context_policy"]["needs_work_context"])
        self.assertEqual(context["work"]["recent_summary"]["latest_activity_type"], "coding")
        self.assertEqual(context["work"]["recent_activities"][0]["app_name"], "VS Code")

    def test_build_for_text_preserves_base_payload(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())
        payload = {"text": "我刚刚在做什么", "session_id": "s1"}

        context = builder.build_for_text(
            "我刚刚在做什么",
            base_context={"payload": payload},
        )

        self.assertEqual(context["payload"], payload)
        self.assertIn("work", context)

    def test_memory_error_adds_context_errors(self) -> None:
        builder = ContextBuilder(memory_store=RaisingContextMemory())

        context = builder.build_for_text("我刚刚在做什么")

        self.assertNotIn("work", context)
        self.assertEqual(context["context_errors"][0]["scope"], "work")
        self.assertIn("work memory unavailable", context["context_errors"][0]["error"])

    def test_matched_keywords_enter_context_policy(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build_for_text("继续刚才的项目")

        self.assertEqual(context["context_policy"]["matched_keywords"], [
            "刚才",
            "继续",
            "继续刚才",
            "项目",
        ])

    def test_build_compatibility_uses_trigger_text(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build({
            "payload": {"text": "今天天气怎么样"},
            "text": "我刚刚在做什么",
        })

        self.assertIn("work", context)
        self.assertEqual(context["text"], "我刚刚在做什么")

    def test_build_compatibility_uses_payload_text(self) -> None:
        builder = ContextBuilder(memory_store=FakeContextMemory())

        context = builder.build({"payload": {"text": "我刚刚在做什么"}})

        self.assertIn("work", context)

    def test_none_memory_store_work_text_does_not_crash(self) -> None:
        builder = ContextBuilder(memory_store=None)

        context = builder.build_for_text("我刚刚在做什么")

        self.assertTrue(context["context_policy"]["needs_work_context"])
        self.assertNotIn("work", context)


if __name__ == "__main__":
    unittest.main()
