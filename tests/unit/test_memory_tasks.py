"""Unit tests for task memory APIs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore


class MemoryTasksTest(unittest.TestCase):
    def _store(self, temp_dir: str) -> XiaoAnMemoryStore:
        return XiaoAnMemoryStore(db_path=str(Path(temp_dir) / "tasks.db"))

    def test_insert_task_writes_event_and_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                result = store.insert_task(
                    title="write tests",
                    description="cover task store",
                    due_text="tomorrow",
                    priority="high",
                    project_hint="xiao-an-robot",
                    metadata={"source": "unit"},
                )

                self.assertIsInstance(result["event_id"], int)
                self.assertIsInstance(result["task_id"], int)
                event = store.get_event(result["event_id"])
                self.assertEqual(event["event_type"], "task.added")
                self.assertEqual(event["payload"]["title"], "write tests")
                tasks = store.query_tasks()
                self.assertEqual(tasks[0]["title"], "write tests")
                self.assertEqual(tasks[0]["priority"], "high")
                self.assertEqual(tasks[0]["metadata"], {"source": "unit"})

    def test_insert_task_empty_title_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                with self.assertRaises(ValueError):
                    store.insert_task("")

    def test_query_tasks_defaults_to_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                pending = store.insert_task("pending")
                done = store.insert_task("done")
                store.complete_task(task_id=done["task_id"])

                tasks = store.query_tasks()

                self.assertEqual(len(tasks), 1)
                self.assertEqual(tasks[0]["id"], pending["task_id"])

    def test_query_tasks_status_done_returns_done(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                done = store.insert_task("done")
                store.complete_task(task_id=done["task_id"])

                tasks = store.query_tasks(status="done")

                self.assertEqual(len(tasks), 1)
                self.assertEqual(tasks[0]["status"], "done")

    def test_complete_task_by_id_writes_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                task = store.insert_task("finish api")

                result = store.complete_task(task_id=task["task_id"])

                self.assertTrue(result["ok"])
                done_tasks = store.query_tasks(status="done")
                self.assertEqual(done_tasks[0]["title"], "finish api")
                event = store.get_event(result["event_id"])
                self.assertEqual(event["event_type"], "task.completed")
                self.assertEqual(event["payload"]["status"], "done")

    def test_complete_task_by_title_contains(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_task("finish docs")

                result = store.complete_task(title_contains="docs")

                self.assertTrue(result["ok"])
                self.assertEqual(result["title"], "finish docs")

    def test_complete_task_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                result = store.complete_task(title_contains="missing")

                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], "not_found")

    def test_cancel_task_by_id_writes_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                task = store.insert_task("cancel me")

                result = store.cancel_task(task_id=task["task_id"])

                self.assertTrue(result["ok"])
                cancelled_tasks = store.query_tasks(status="cancelled")
                self.assertEqual(cancelled_tasks[0]["title"], "cancel me")
                event = store.get_event(result["event_id"])
                self.assertEqual(event["event_type"], "task.cancelled")

    def test_get_tasks_summary_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                summary = store.get_tasks_summary()

                self.assertEqual(summary["count"], 0)
                self.assertEqual(summary["pending_count"], 0)
                self.assertEqual(summary["status_count"], {})

    def test_get_tasks_summary_counts_status_and_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_task("pending", priority="high", project_hint="p1")
                done = store.insert_task("done", priority="low", project_hint="p1")
                cancelled = store.insert_task("cancelled", priority="weird", project_hint="p2")
                store.complete_task(task_id=done["task_id"])
                store.cancel_task(task_id=cancelled["task_id"])

                summary = store.get_tasks_summary()

                self.assertEqual(summary["count"], 3)
                self.assertEqual(summary["pending_count"], 1)
                self.assertEqual(summary["done_count"], 1)
                self.assertEqual(summary["cancelled_count"], 1)
                self.assertEqual(summary["high_priority_count"], 1)
                self.assertEqual(summary["priority_count"]["normal"], 1)
                self.assertEqual(summary["project_hint_count"]["p1"], 2)
                self.assertEqual(summary["latest_task_title"], "cancelled")

    def test_metadata_json_parses_to_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_task("with metadata", metadata={"a": 1})

                tasks = store.query_tasks()

                self.assertEqual(tasks[0]["metadata"], {"a": 1})


if __name__ == "__main__":
    unittest.main()
