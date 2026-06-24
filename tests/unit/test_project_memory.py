"""Unit tests for project-level memory recording."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore
from agent.core.project_memory import ProjectMemoryService


class ProjectMemoryServiceTest(unittest.TestCase):
    def make_store(self, temp_dir: str) -> XiaoAnMemoryStore:
        return XiaoAnMemoryStore(str(Path(temp_dir) / "project_memory.db"))

    def test_record_note_writes_note_and_memory_event(self) -> None:
        class CustomPayload:
            def __str__(self) -> str:
                return "custom-payload"

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)

                result = service.record_note(
                    "remember the project decision",
                    session_id="session-note",
                    payload={"project_hint": "xiao-an-robot", "custom": CustomPayload()},
                    tags=["decision"],
                )

                note = store.query_recent_notes()[0]
                event = store.get_event(result["event_id"])
                self.assertEqual(note["content"], "remember the project decision")
                self.assertEqual(note["tags"], ["decision"])
                self.assertEqual(event["event_type"], "note.add")
                self.assertEqual(event["session_id"], "session-note")
                self.assertEqual(event["payload"]["custom"], "custom-payload")

    def test_record_work_activity_writes_activity_and_memory_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)

                result = service.record_work_activity(
                    "editing project memory",
                    session_id="session-work",
                    payload={
                        "app_name": "VS Code",
                        "activity_type": "coding",
                        "project_hint": "xiao-an-robot",
                        "confidence": 0.9,
                    },
                )

                activity = store.query_recent_work_activities()[0]
                event = store.get_event(result["event_id"])
                self.assertEqual(activity["window_title"], "editing project memory")
                self.assertEqual(activity["activity_type"], "coding")
                self.assertEqual(event["event_type"], "work_context.record")
                self.assertEqual(event["session_id"], "session-work")

    def test_record_summary_writes_summary_and_memory_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)

                result = service.record_summary(
                    "completed the project memory service",
                    session_id="session-summary",
                    payload={"title": "Daily", "date": "2026-06-20"},
                )

                summary = store.query_recent_summaries()[0]
                event = store.get_event(result["event_id"])
                self.assertEqual(summary["summary_type"], "daily")
                self.assertEqual(summary["content"], "completed the project memory service")
                self.assertEqual(event["event_type"], "summary.daily")
                self.assertEqual(event["session_id"], "session-summary")

    def test_record_tool_run_success_writes_run_and_memory_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)

                result = service.record_tool_run(
                    "note.add",
                    arguments={"content": "hello"},
                    result={"saved": True},
                    session_id="session-tool",
                )

                run = store.query_recent_tool_runs()[0]
                event = store.get_event(result["event_id"])
                self.assertTrue(result["ok"])
                self.assertEqual(run["status"], "success")
                self.assertIsNone(run["source_event_type"])
                self.assertEqual(event["event_type"], "tool.run")
                self.assertEqual(event["source"], "openclaw")
                self.assertEqual(event["session_id"], "session-tool")

    def test_query_services_filter_and_return_lightweight_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)
                service.record_note("release report decision")
                service.record_note("unrelated note")
                service.record_work_activity(
                    "implement Step 27 query",
                    payload={"app_name": "VS Code", "project_hint": "xiao-an-robot"},
                )
                service.record_summary(
                    "summary keyword " + ("long content " * 30),
                    payload={"title": "Step 27 summary", "date": "2026-06-22"},
                )

                notes = service.search_notes(keyword="report")
                activities = service.query_work_activities(keyword="Step 27")
                summaries = service.query_summaries(
                    date="2026-06-22",
                    keyword="keyword",
                )

                self.assertEqual(
                    [row["content"] for row in notes],
                    ["release report decision"],
                )
                self.assertEqual(activities[0]["app_name"], "VS Code")
                self.assertEqual(summaries[0]["title"], "Step 27 summary")
                self.assertNotIn("content", summaries[0])
                self.assertLessEqual(len(summaries[0]["content_preview"]), 160)
                self.assertEqual(service.search_notes(keyword="missing"), [])
                self.assertEqual(service.query_work_activities(keyword="missing"), [])
                self.assertEqual(service.query_summaries(keyword="missing"), [])

    def test_record_tool_run_keeps_source_event_type_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)

                result = service.record_tool_run(
                    "task.query",
                    source="openclaw",
                    source_event_type="frontend.message",
                )

                run = store.query_recent_tool_runs()[0]
                event = store.get_event(result["event_id"])
                self.assertEqual(run["source_event_type"], "frontend.message")
                self.assertEqual(event["source"], "openclaw")

    def test_record_tool_run_failure_records_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)

                result = service.record_tool_run(
                    "summary.daily",
                    ok=False,
                    error="summary failed",
                    result={"exception": ValueError("bad input")},
                )

                run = store.query_recent_tool_runs()[0]
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "failed")
                self.assertEqual(run["status"], "failed")
                self.assertEqual(run["error"], "summary failed")
                self.assertEqual(run["result"]["exception"], "bad input")

    def test_task_service_records_queries_completes_and_cancels_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)
                pending = service.record_task(
                    "pending task",
                    priority="high",
                    project_hint="xiao-an-robot",
                    metadata={"kind": "unit"},
                )
                done = service.record_task("done task")
                cancelled = service.record_task("cancelled task")

                complete_result = service.complete_task(task_id=done["task_id"])
                cancel_result = service.cancel_task(
                    title_contains="cancelled",
                )

                self.assertEqual(complete_result["status"], "done")
                self.assertEqual(cancel_result["status"], "cancelled")
                self.assertEqual(
                    service.query_tasks()[0]["id"],
                    pending["task_id"],
                )
                self.assertEqual(
                    service.query_tasks(status="done")[0]["id"],
                    done["task_id"],
                )
                self.assertEqual(
                    service.query_tasks(status="cancelled")[0]["id"],
                    cancelled["task_id"],
                )
                self.assertEqual(len(service.query_tasks(status="all")), 3)
                event_types = [
                    event["event_type"]
                    for event in store.query_recent_events(limit=10)
                ]
                self.assertEqual(event_types.count("task.added"), 3)
                self.assertIn("task.completed", event_types)
                self.assertIn("task.cancelled", event_types)

    def test_task_service_not_found_has_product_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)

                complete_result = service.complete_task(title_contains="missing")
                cancel_result = service.cancel_task(task_id=999)

                self.assertFalse(complete_result["ok"])
                self.assertEqual(complete_result["error"], "task_not_found")
                self.assertFalse(cancel_result["ok"])
                self.assertEqual(cancel_result["error"], "task_not_found")

    def test_reminder_service_records_queries_and_cancels_reminders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)
                pending = service.record_reminder(
                    "pending reminder",
                    delay_seconds=60,
                    due_text="in one minute",
                    metadata={"kind": "unit"},
                )
                fired = service.record_reminder("fired reminder", delay_seconds=60)
                cancelled = service.record_reminder(
                    "cancelled reminder",
                    date="2026-06-23",
                )
                store.mark_reminder_fired(fired["reminder_id"])

                cancel_result = service.cancel_reminder(
                    reminder_id=cancelled["reminder_id"],
                )

                self.assertEqual(cancel_result["status"], "cancelled")
                self.assertEqual(
                    service.query_reminders()[0]["id"],
                    pending["reminder_id"],
                )
                self.assertEqual(
                    service.query_reminders(status="fired")[0]["id"],
                    fired["reminder_id"],
                )
                cancelled_rows = service.query_reminders(status="cancelled")
                self.assertEqual(cancelled_rows[0]["id"], cancelled["reminder_id"])
                self.assertEqual(len(service.query_reminders(status="all")), 3)
                self.assertEqual(
                    service.query_reminders()[0]["metadata"]["due_text"],
                    "in one minute",
                )
                summary = service.get_reminders_summary()
                self.assertEqual(summary["pending_count"], 1)
                self.assertEqual(summary["fired_count"], 1)
                self.assertEqual(summary["cancelled_count"], 1)
                event_types = [
                    event["event_type"]
                    for event in store.query_recent_events(limit=10)
                ]
                self.assertEqual(event_types.count("reminder.added"), 3)
                self.assertIn("reminder.cancelled", event_types)

    def test_reminder_service_not_found_has_product_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)

                result = service.cancel_reminder(reminder_id=999)

                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], "reminder_not_found")

    def test_get_recent_project_context_returns_all_memory_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)
                service.record_note("project note")
                service.record_work_activity("project work")
                service.record_summary("project summary")
                service.record_tool_run("note.add")
                store.insert_event(
                    event_type="robot.care_action",
                    source="brain",
                    text="care action",
                    payload={"large": "hidden"},
                )

                context = service.get_recent_project_context(limit=10)

                self.assertEqual(context["scope"], "all")
                self.assertEqual(context["notes_count"], 1)
                self.assertEqual(context["summary_overview"]["count"], 1)
                self.assertEqual(context["work_summary"]["count"], 1)
                self.assertEqual(context["tool_run_summary"]["count"], 1)
                self.assertEqual(context["memory_events_count"], 5)
                self.assertEqual(
                    context["recent_care_events"][0]["event_type"],
                    "robot.care_action",
                )
                self.assertNotIn("payload", context["recent_care_events"][0])

                notes_only = service.get_recent_project_context(scope="notes")
                self.assertIn("recent_notes", notes_only)
                self.assertNotIn("recent_tool_runs", notes_only)

    def test_project_context_supports_tasks_and_reminders_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_store(temp_dir) as store:
                service = ProjectMemoryService(memory_store=store)
                for index in range(7):
                    service.record_task(f"pending task {index}")
                    service.record_reminder(
                        f"pending reminder {index}",
                        delay_seconds=60,
                    )

                tasks = service.get_recent_project_context(
                    limit=10,
                    scope="tasks",
                )
                reminders = service.get_recent_project_context(
                    limit=10,
                    scope="reminders",
                )

                self.assertEqual(len(tasks["recent_tasks"]), 5)
                self.assertEqual(tasks["tasks_summary"]["pending_count"], 7)
                self.assertTrue(
                    all(row["status"] == "pending" for row in tasks["recent_tasks"]),
                )
                self.assertEqual(len(reminders["recent_reminders"]), 5)
                self.assertEqual(
                    reminders["reminders_summary"]["pending_count"],
                    7,
                )
                self.assertNotIn("metadata", reminders["recent_reminders"][0])


if __name__ == "__main__":
    unittest.main()
