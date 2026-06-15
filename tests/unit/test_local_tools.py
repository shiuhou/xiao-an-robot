"""Unit tests for local OpenClaw placeholder tools."""

from __future__ import annotations

import unittest

from agent.core.local_tools import LocalToolRegistry


class FakeMemoryStore:
    def __init__(self, raise_error: bool = False) -> None:
        self.raise_error = raise_error
        self.notes = []
        self.summaries = []
        self.work_activities = []

    def insert_note(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        self.notes.append(kwargs)
        return {"event_id": len(self.notes), "note_id": len(self.notes)}

    def insert_summary(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        self.summaries.append(kwargs)
        return {"event_id": len(self.summaries), "summary_id": len(self.summaries)}

    def insert_work_activity(self, **kwargs) -> dict:
        self.work_activities.append(kwargs)
        return {"event_id": 999, "work_activity_id": 999}

    def get_recent_work_summary(self) -> dict:
        return {"count": 2}

    def get_notes_summary(self) -> dict:
        return {"count": len(self.notes)}

    def get_tool_run_summary(self) -> dict:
        return {"count": 3}


class LocalToolRegistryTest(unittest.TestCase):
    def test_note_add_returns_placeholder_result(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("note.add", {"content": "记一下", "tags": ["work"]})

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "note.add")
        self.assertEqual(result["result"]["content"], "记一下")
        self.assertEqual(result["result"]["tags"], ["work"])

    def test_work_context_record_returns_placeholder_result(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("work_context.record", {"content": "写项目代码", "source": "frontend"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "work_context.record")
        self.assertEqual(result["result"]["content"], "写项目代码")
        self.assertEqual(result["result"]["source"], "frontend")

    def test_summary_daily_returns_placeholder_status(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("summary.daily", {"date": "2026-06-13"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "summary.daily")
        self.assertEqual(result["result"]["date"], "2026-06-13")
        self.assertEqual(result["result"]["status"], "placeholder")

    def test_none_arguments_do_not_crash(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("note.add", None)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["content"], "")
        self.assertEqual(result["result"]["tags"], [])

    def test_unknown_tool_returns_ok_false(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("unknown.tool", {"x": 1})

        self.assertFalse(result["ok"])
        self.assertEqual(result["name"], "unknown.tool")
        self.assertEqual(result["error"], "unsupported local tool")

    def test_note_add_with_memory_store_persists_note(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("note.add", {
            "content": "remember this",
            "tags": ["work"],
            "project_hint": "xiao-an-robot",
        })

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["persisted"])
        self.assertEqual(result["result"]["note_result"], {"event_id": 1, "note_id": 1})
        self.assertEqual(memory_store.notes[0]["content"], "remember this")
        self.assertEqual(memory_store.notes[0]["tags"], ["work"])
        self.assertEqual(memory_store.notes[0]["project_hint"], "xiao-an-robot")

    def test_note_add_without_memory_store_remains_placeholder(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("note.add", {"content": "remember this"})

        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["persisted"])
        self.assertEqual(result["result"]["content"], "remember this")

    def test_work_context_record_with_memory_store_persists_note_only(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("work_context.record", {
            "text": "coding memory layer",
            "tags": ["coding", "work_context"],
            "project_hint": "xiao-an-robot",
        })

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["persisted"])
        self.assertEqual(memory_store.notes[0]["content"], "coding memory layer")
        self.assertEqual(memory_store.notes[0]["tags"], ["work_context", "coding"])
        self.assertEqual(memory_store.notes[0]["project_hint"], "xiao-an-robot")
        self.assertEqual(memory_store.work_activities, [])

    def test_work_context_record_default_tags_include_work_context(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("work_context.record", {"content": "note"})

        self.assertTrue(result["ok"])
        self.assertIn("work_context", result["result"]["tags"])
        self.assertEqual(memory_store.notes[0]["tags"], ["work_context"])

    def test_work_context_record_without_memory_store_remains_placeholder(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("work_context.record", {"content": "coding"})

        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["persisted"])
        self.assertEqual(result["result"]["content"], "coding")

    def test_summary_daily_with_memory_store_persists_summary(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("summary.daily", {"date": "2026-06-16"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["persisted"])
        self.assertEqual(result["result"]["summary_result"], {"event_id": 1, "summary_id": 1})
        self.assertEqual(memory_store.summaries[0]["summary_type"], "daily")
        self.assertEqual(memory_store.summaries[0]["date"], "2026-06-16")
        self.assertIn("Daily summary for 2026-06-16", memory_store.summaries[0]["content"])

    def test_memory_store_error_returns_ok_false(self) -> None:
        memory_store = FakeMemoryStore(raise_error=True)
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("note.add", {"content": "remember this"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["name"], "note.add")
        self.assertIn("memory unavailable", result["error"])


if __name__ == "__main__":
    unittest.main()
