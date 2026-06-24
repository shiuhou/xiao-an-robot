"""Unit tests for local OpenClaw placeholder tools."""

from __future__ import annotations

import unittest

from agent.core.local_tools import LocalToolRegistry


class FakeMemoryStore:
    def __init__(
        self,
        raise_error: bool = False,
        raise_summary_query: bool = False,
        raise_insert_summary: bool = False,
    ) -> None:
        self.raise_error = raise_error
        self.raise_summary_query = raise_summary_query
        self.raise_insert_summary = raise_insert_summary
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
        if self.raise_error or self.raise_insert_summary:
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

    def get_recent_work_summary(self, limit: int = 20) -> dict:
        return {
            "count": 2,
            "top_activity_type": "coding",
            "top_app_name": "VS Code",
            "latest_project_hint": "xiao-an-robot",
        }

    def query_recent_work_activities(
        self,
        limit: int = 20,
        activity_type=None,
        project_hint=None,
        keyword=None,
    ) -> list[dict]:
        rows = self.work_activities
        if project_hint is not None:
            rows = [row for row in rows if row.get("project_hint") == project_hint]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("window_title", ""))
                or keyword in str(row.get("app_name", ""))
            ]
        return rows[:limit]

    def get_notes_summary(self, limit: int = 20) -> dict:
        return {"count": len(self.notes)}

    def query_recent_notes(
        self,
        limit: int = 20,
        project_hint=None,
        keyword=None,
    ) -> list[dict]:
        if self.raise_summary_query:
            raise RuntimeError("notes query failed")
        rows = self.notes
        if project_hint is not None:
            rows = [row for row in rows if row.get("project_hint") == project_hint]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("content", ""))]
        return rows[:limit]

    def query_recent_summaries(
        self,
        limit: int = 20,
        summary_type=None,
        date=None,
        keyword=None,
    ) -> list[dict]:
        rows = self.summaries
        if summary_type is not None:
            rows = [row for row in rows if row.get("summary_type") == summary_type]
        if date is not None:
            rows = [row for row in rows if row.get("date") == date]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("title", ""))
                or keyword in str(row.get("content", ""))
            ]
        return rows[:limit]

    def get_tool_run_summary(self, limit: int = 20) -> dict:
        return {"count": 3, "tool_count": {"note.add": 1, "summary.daily": 1}}

    def query_recent_tool_runs(self, limit: int = 20) -> list[dict]:
        return []

    def get_tasks_summary(self, limit: int = 20) -> dict:
        status_count = {}
        for task in self.tasks:
            status = task.get("status")
            status_count[status] = status_count.get(status, 0) + 1
        return {
            "count": len(self.tasks),
            "pending_count": status_count.get("pending", 0),
            "done_count": status_count.get("done", 0),
            "cancelled_count": status_count.get("cancelled", 0),
        }

    def get_reminders_summary(self, limit: int = 20) -> dict:
        status_count = {}
        for reminder in self.reminders:
            status = reminder.get("status")
            status_count[status] = status_count.get(status, 0) + 1
        return {
            "count": len(self.reminders),
            "pending_count": status_count.get("pending", 0),
            "fired_count": status_count.get("fired", 0),
            "cancelled_count": status_count.get("cancelled", 0),
        }

    def get_emotion_summary(self, hours: int = 24) -> dict:
        return {"count": 0}


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

    def test_work_context_record_with_memory_store_persists_work_activity(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("work_context.record", {
            "text": "coding memory layer",
            "tags": ["coding", "work_context"],
            "project_hint": "xiao-an-robot",
        })

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["persisted"])
        self.assertEqual(memory_store.notes, [])
        self.assertEqual(memory_store.work_activities[0]["window_title"], "coding memory layer")
        self.assertEqual(memory_store.work_activities[0]["activity_type"], "work_context")
        self.assertEqual(memory_store.work_activities[0]["project_hint"], "xiao-an-robot")
        self.assertEqual(memory_store.work_activities[0]["event_type"], "work_context.record")
        self.assertEqual(memory_store.work_activities[0]["event_payload"]["tags"], ["work_context", "coding"])

    def test_work_context_record_default_tags_include_work_context(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("work_context.record", {"content": "note"})

        self.assertTrue(result["ok"])
        self.assertIn("work_context", result["result"]["tags"])
        self.assertEqual(memory_store.work_activities[0]["event_payload"]["tags"], ["work_context"])

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
        self.assertIn("小安日报 - 2026-06-16", memory_store.summaries[0]["content"])

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

    def test_reminder_add_accepts_content_and_text_message_aliases(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        content_result = registry.execute(
            "reminder.add",
            {"content": "from content", "delay_seconds": 60},
        )
        text_result = registry.execute(
            "reminder.add",
            {"text": "from text", "due_at_ms": 2000},
        )

        self.assertTrue(content_result["result"]["persisted"])
        self.assertTrue(text_result["result"]["persisted"])
        self.assertEqual(
            [reminder["message"] for reminder in memory_store.reminders],
            ["from content", "from text"],
        )

    def test_reminder_add_validation_returns_product_errors(self) -> None:
        registry = LocalToolRegistry(memory_store=FakeMemoryStore())

        missing_message = registry.execute(
            "reminder.add",
            {"delay_seconds": 60},
        )
        missing_time = registry.execute(
            "reminder.add",
            {"message": "wake me"},
        )

        self.assertFalse(missing_message["ok"])
        self.assertEqual(missing_message["error"], "missing_reminder_message")
        self.assertFalse(missing_time["ok"])
        self.assertEqual(missing_time["error"], "missing_reminder_time")
        self.assertTrue(missing_time["needs_time_clarification"])

    def test_reminder_query_returns_pending_reminders(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("reminder.add", {"message": "wake me", "delay_seconds": 60})

        result = registry.execute("reminder.query", {"status": "pending"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["reminders"][0]["message"], "wake me")

    def test_reminder_query_supports_all_and_empty_results(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        added = registry.execute(
            "reminder.add",
            {"message": "cancel me", "delay_seconds": 60},
        )
        registry.execute(
            "reminder.cancel",
            {"reminder_id": added["result"]["reminder_result"]["reminder_id"]},
        )

        all_result = registry.execute("reminder.query", {"status": "all"})
        empty_result = registry.execute("reminder.query", {"status": "pending"})

        self.assertTrue(all_result["ok"])
        self.assertEqual(all_result["count"], 1)
        self.assertEqual(all_result["reminders"][0]["status"], "cancelled")
        self.assertTrue(empty_result["ok"])
        self.assertEqual(empty_result["reminders"], [])

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
        self.assertEqual(result["error"], "reminder_not_found")

    def test_reminder_cancel_supports_reminder_id_and_text_alias(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        first = registry.execute(
            "reminder.add",
            {"message": "cancel by id", "delay_seconds": 60},
        )
        registry.execute(
            "reminder.add",
            {"message": "cancel by text", "delay_seconds": 60},
        )

        by_id = registry.execute(
            "reminder.cancel",
            {
                "reminder_id": first["result"]["reminder_result"]["reminder_id"],
                "text": "ignored",
            },
        )
        by_text = registry.execute("reminder.cancel", {"text": "by text"})

        self.assertTrue(by_id["ok"])
        self.assertEqual(by_id["result"]["cancel_result"]["status"], "cancelled")
        self.assertTrue(by_text["ok"])
        self.assertEqual(memory_store.reminders[1]["status"], "cancelled")

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

    def test_task_add_accepts_content_and_text_title_aliases(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)

        content_result = registry.execute("task.add", {"content": "from content"})
        text_result = registry.execute("task.add", {"text": "from text"})

        self.assertTrue(content_result["result"]["persisted"])
        self.assertTrue(text_result["result"]["persisted"])
        self.assertEqual(
            [task["title"] for task in memory_store.tasks],
            ["from content", "from text"],
        )

    def test_task_add_missing_title_returns_product_error(self) -> None:
        registry = LocalToolRegistry(memory_store=FakeMemoryStore())

        result = registry.execute("task.add", {})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_task_title")

    def test_task_query_returns_pending_tasks(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("task.add", {"title": "write tests"})

        result = registry.execute("task.query", {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tasks"][0]["title"], "write tests")

    def test_task_query_supports_all_and_empty_results(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        first = registry.execute("task.add", {"title": "done task"})
        registry.execute(
            "task.complete",
            {"task_id": first["result"]["task_result"]["task_id"]},
        )

        all_result = registry.execute("task.query", {"status": "all"})
        empty_result = registry.execute(
            "task.query",
            {"status": "pending", "project_hint": "missing"},
        )

        self.assertTrue(all_result["ok"])
        self.assertEqual(all_result["count"], 1)
        self.assertEqual(all_result["tasks"][0]["status"], "done")
        self.assertTrue(empty_result["ok"])
        self.assertEqual(empty_result["tasks"], [])

    def test_task_complete_completes_task(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("task.add", {"title": "write tests"})

        result = registry.execute("task.complete", {"title_contains": "tests"})

        self.assertTrue(result["ok"])
        self.assertEqual(memory_store.tasks[0]["status"], "done")
        self.assertEqual(result["result"]["task_result"]["task_id"], 1)

    def test_task_complete_supports_task_id_and_text_match(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        first = registry.execute("task.add", {"title": "complete by id"})
        registry.execute("task.add", {"title": "complete by text"})

        by_id = registry.execute(
            "task.complete",
            {"task_id": first["result"]["task_result"]["task_id"], "text": "ignored"},
        )
        by_text = registry.execute("task.complete", {"text": "by text"})

        self.assertTrue(by_id["ok"])
        self.assertEqual(by_id["result"]["task_result"]["status"], "done")
        self.assertTrue(by_text["ok"])
        self.assertEqual(memory_store.tasks[1]["status"], "done")

    def test_task_cancel_cancels_task(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("task.add", {"title": "write tests"})

        result = registry.execute("task.cancel", {"title_contains": "tests"})

        self.assertTrue(result["ok"])
        self.assertEqual(memory_store.tasks[0]["status"], "cancelled")

    def test_task_cancel_supports_task_id_and_content_match(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        first = registry.execute("task.add", {"title": "cancel by id"})
        registry.execute("task.add", {"title": "cancel by content"})

        by_id = registry.execute(
            "task.cancel",
            {"task_id": first["result"]["task_result"]["task_id"]},
        )
        by_content = registry.execute(
            "task.cancel",
            {"content": "by content"},
        )

        self.assertTrue(by_id["ok"])
        self.assertEqual(by_id["result"]["task_result"]["status"], "cancelled")
        self.assertTrue(by_content["ok"])
        self.assertEqual(memory_store.tasks[1]["status"], "cancelled")

    def test_task_complete_not_found_returns_ok_false(self) -> None:
        registry = LocalToolRegistry(memory_store=FakeMemoryStore())

        result = registry.execute("task.complete", {"title_contains": "missing"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "task_not_found")
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

    def test_summary_daily_returns_summary_field(self) -> None:
        registry = LocalToolRegistry(memory_store=FakeMemoryStore())

        result = registry.execute("summary.daily", {"date": "2026-06-16"})

        self.assertTrue(result["ok"])
        self.assertIn("summary", result["result"])
        self.assertEqual(result["result"]["summary"]["summary_type"], "daily")

    def test_summary_daily_content_includes_memory_data(self) -> None:
        memory_store = FakeMemoryStore()
        memory_store.insert_note(content="明天下午交报告")
        memory_store.insert_task(title="完成日报", status="pending")
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute("summary.daily", {"date": "2026-06-16"})

        content = result["result"]["summary"]["content"]
        self.assertIn("明天下午交报告", content)
        self.assertIn("完成日报", content)
        self.assertIn("coding", content)
        self.assertIn("VS Code", content)

    def test_summary_daily_query_error_still_generates(self) -> None:
        registry = LocalToolRegistry(memory_store=FakeMemoryStore(raise_summary_query=True))

        result = registry.execute("summary.daily", {"date": "2026-06-16"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["summary"]["content"])
        self.assertEqual(result["result"]["summary"]["metadata"]["errors"][0]["scope"], "query_recent_notes")

    def test_summary_daily_insert_failure_returns_ok_false(self) -> None:
        registry = LocalToolRegistry(memory_store=FakeMemoryStore(raise_insert_summary=True))

        result = registry.execute("summary.daily", {"date": "2026-06-16"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["name"], "summary.daily")
        self.assertIn("memory unavailable", result["error"])

    def test_note_search_finds_notes_and_empty_is_success(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute("note.add", {"content": "prepare release report"})

        found = registry.execute("note.search", {"text": "report"})
        missing = registry.execute("note.search", {"keyword": "missing"})

        self.assertTrue(found["ok"])
        self.assertEqual(found["items"][0]["content"], "prepare release report")
        self.assertEqual(found["notes"], found["items"])
        self.assertTrue(missing["ok"])
        self.assertEqual(missing["items"], [])

    def test_work_context_query_finds_activity_and_empty_is_success(self) -> None:
        memory_store = FakeMemoryStore()
        registry = LocalToolRegistry(memory_store=memory_store)
        registry.execute(
            "work_context.record",
            {"content": "implement Step 27 query", "app_name": "VS Code"},
        )

        found = registry.execute("work_context.query", {"text": "Step 27"})
        missing = registry.execute("work_context.query", {"keyword": "missing"})

        self.assertTrue(found["ok"])
        self.assertEqual(found["items"][0]["window_title"], "implement Step 27 query")
        self.assertEqual(found["work_activities"], found["items"])
        self.assertTrue(missing["ok"])
        self.assertEqual(missing["items"], [])

    def test_summary_query_returns_lightweight_preview(self) -> None:
        memory_store = FakeMemoryStore()
        memory_store.insert_summary(
            summary_type="daily",
            title="Daily report",
            date="2026-06-16",
            content="x" * 300,
        )
        registry = LocalToolRegistry(memory_store=memory_store)

        result = registry.execute(
            "summary.query",
            {"date": "2026-06-16", "summary_type": "daily"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertNotIn("content", result["items"][0])
        self.assertLessEqual(len(result["items"][0]["content_preview"]), 160)

    def test_query_tools_without_memory_store_return_empty_placeholders(self) -> None:
        registry = LocalToolRegistry()

        for name in ("note.search", "work_context.query", "summary.query"):
            with self.subTest(name=name):
                result = registry.execute(name, {})
                self.assertTrue(result["ok"])
                self.assertFalse(result["persisted"])
                self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
