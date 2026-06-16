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
        self.reminders = []
        self.tasks = []

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

    def insert_reminder(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        reminder = dict(kwargs)
        reminder["id"] = len(self.reminders) + 1
        reminder["status"] = "pending"
        self.reminders.append(reminder)
        return {"event_id": len(self.reminders), "reminder_id": len(self.reminders), "due_at_ms": 1234}

    def query_reminders(self, limit: int = 20, status: str | None = None, include_fired: bool = False) -> list[dict]:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        reminders = self.reminders
        if status is not None:
            reminders = [item for item in reminders if item.get("status") == status]
        elif not include_fired:
            reminders = [item for item in reminders if item.get("status") == "pending"]
        return reminders[:limit]

    def cancel_reminder(self, reminder_id=None, message_contains=None, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        for reminder in self.reminders:
            id_matches = reminder_id is not None and reminder["id"] == int(reminder_id)
            text_matches = message_contains and message_contains in reminder["message"]
            if reminder.get("status") == "pending" and (id_matches or text_matches):
                reminder["status"] = "cancelled"
                return {"ok": True, "event_id": 99, "reminder_id": reminder["id"], "message": reminder["message"]}
        return {"ok": False, "reason": "not_found"}

    def insert_task(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        task = dict(kwargs)
        task["id"] = len(self.tasks) + 1
        task["status"] = "pending"
        self.tasks.append(task)
        return {"event_id": len(self.tasks), "task_id": len(self.tasks)}

    def query_tasks(
        self,
        limit: int = 20,
        status: str | None = None,
        project_hint: str | None = None,
        include_done: bool = False,
    ) -> list[dict]:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        tasks = self.tasks
        if status is not None:
            tasks = [item for item in tasks if item.get("status") == status]
        elif not include_done:
            tasks = [item for item in tasks if item.get("status") == "pending"]
        if project_hint is not None:
            tasks = [item for item in tasks if item.get("project_hint") == project_hint]
        return tasks[:limit]

    def complete_task(self, task_id=None, title_contains=None, **kwargs) -> dict:
        return self._set_task_status("done", task_id=task_id, title_contains=title_contains)

    def cancel_task(self, task_id=None, title_contains=None, **kwargs) -> dict:
        return self._set_task_status("cancelled", task_id=task_id, title_contains=title_contains)

    def _set_task_status(self, status: str, task_id=None, title_contains=None) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        for task in self.tasks:
            id_matches = task_id is not None and task["id"] == int(task_id)
            text_matches = title_contains and title_contains in task["title"]
            if task.get("status") == "pending" and (id_matches or text_matches):
                task["status"] = status
                return {"ok": True, "event_id": 100, "task_id": task["id"], "title": task["title"]}
        return {"ok": False, "reason": "not_found"}

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

    def test_reminder_add_with_memory_store_persists(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("reminder.add", {"message": "wake me", "delay_seconds": 60})

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["persisted"])
        self.assertEqual(result["result"]["reminder_result"]["reminder_id"], 1)
        self.assertEqual(memory_store.reminders[0]["message"], "wake me")

    def test_reminder_query_returns_pending_reminders(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("reminder.add", {"message": "wake me", "delay_seconds": 60})

        result = registry.execute("reminder.query", {"status": "pending"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["reminders"][0]["message"], "wake me")

    def test_reminder_cancel_cancels_reminder(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("reminder.add", {"message": "wake me", "delay_seconds": 60})

        result = registry.execute("reminder.cancel", {"message_contains": "wake"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["cancel_result"]["reminder_id"], 1)
        self.assertEqual(memory_store.reminders[0]["status"], "cancelled")

    def test_reminder_cancel_not_found_returns_ok_false(self) -> None:
        registry = LocalToolRegistry(memory_store=FakeMemoryStore())

        result = registry.execute("reminder.cancel", {"message_contains": "missing"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "not_found")

    def test_reminder_tools_without_memory_store_do_not_crash(self) -> None:
        registry = LocalToolRegistry()

        add_result = registry.execute("reminder.add", {"message": "wake me", "delay_seconds": 60})
        query_result = registry.execute("reminder.query", {})
        cancel_result = registry.execute("reminder.cancel", {"message_contains": "wake"})

        self.assertTrue(add_result["ok"])
        self.assertFalse(add_result["result"]["persisted"])
        self.assertTrue(query_result["ok"])
        self.assertEqual(query_result["reminders"], [])
        self.assertTrue(cancel_result["ok"])
        self.assertFalse(cancel_result["result"]["persisted"])

    def test_task_add_with_memory_store_persists(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("task.add", {"title": "write tests", "priority": "high"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["persisted"])
        self.assertEqual(result["result"]["task_result"]["task_id"], 1)
        self.assertEqual(memory_store.tasks[0]["title"], "write tests")
        self.assertEqual(memory_store.tasks[0]["priority"], "high")

    def test_task_query_returns_pending_tasks(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("task.add", {"title": "write tests"})

        result = registry.execute("task.query", {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tasks"][0]["title"], "write tests")

    def test_task_complete_completes_task(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("task.add", {"title": "write tests"})

        result = registry.execute("task.complete", {"title_contains": "tests"})

        self.assertTrue(result["ok"])
        self.assertEqual(memory_store.tasks[0]["status"], "done")
        self.assertEqual(result["result"]["task_result"]["task_id"], 1)

    def test_task_cancel_cancels_task(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("task.add", {"title": "write tests"})

        result = registry.execute("task.cancel", {"title_contains": "tests"})

        self.assertTrue(result["ok"])
        self.assertEqual(memory_store.tasks[0]["status"], "cancelled")

    def test_task_complete_not_found_returns_ok_false(self) -> None:
        registry = LocalToolRegistry(memory_store=FakeMemoryStore())

        result = registry.execute("task.complete", {"title_contains": "missing"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "not_found")

    def test_task_tools_without_memory_store_do_not_crash(self) -> None:
        registry = LocalToolRegistry()

        add_result = registry.execute("task.add", {"title": "write tests"})
        query_result = registry.execute("task.query", {})
        complete_result = registry.execute("task.complete", {"title_contains": "tests"})
        cancel_result = registry.execute("task.cancel", {"title_contains": "tests"})

        self.assertTrue(add_result["ok"])
        self.assertFalse(add_result["result"]["persisted"])
        self.assertTrue(query_result["ok"])
        self.assertEqual(query_result["tasks"], [])
        self.assertTrue(complete_result["ok"])
        self.assertFalse(complete_result["result"]["persisted"])
        self.assertTrue(cancel_result["ok"])
        self.assertFalse(cancel_result["result"]["persisted"])


if __name__ == "__main__":
    unittest.main()
