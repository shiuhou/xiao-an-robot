"""Unit tests for tool run storage in XiaoAnMemoryStore."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore


class MemoryToolRunsTest(unittest.TestCase):
    def make_db_path(self, temp_dir: str) -> str:
        return str(Path(temp_dir) / "memory_tool_runs.db")

    def test_insert_tool_run_writes_event_and_tool_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                result = db.insert_tool_run(
                    tool_name="robot.say",
                    arguments={"text": "hello"},
                    result={"ok": True},
                    status="success",
                    timestamp_ms=1000,
                )

                events = db.query_recent_events(event_type="tool.run")
                runs = db.query_recent_tool_runs()

                self.assertIsInstance(result["event_id"], int)
                self.assertIsInstance(result["tool_run_id"], int)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["event_type"], "tool.run")
                self.assertEqual(len(runs), 1)
                self.assertEqual(runs[0]["event_id"], events[0]["id"])
                self.assertEqual(runs[0]["arguments"], {"text": "hello"})
                self.assertEqual(runs[0]["result"], {"ok": True})

    def test_query_recent_tool_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_tool_run("note.add", status="success", timestamp_ms=1000)
                db.insert_tool_run("robot.say", status="skipped", timestamp_ms=2000)

                rows = db.query_recent_tool_runs(limit=1)

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["tool_name"], "robot.say")

    def test_tool_name_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_tool_run("note.add", status="success")
                db.insert_tool_run("robot.say", status="success")

                rows = db.query_recent_tool_runs(tool_name="note.add")

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["tool_name"], "note.add")

    def test_status_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_tool_run("note.add", status="success")
                db.insert_tool_run("robot.say", status="failed")

                rows = db.query_recent_tool_runs(status="failed")

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["status"], "failed")

    def test_get_tool_run_summary_counts_statuses_and_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_tool_run("robot.say", status="success", timestamp_ms=1000)
                db.insert_tool_run("robot.say", status="failed", timestamp_ms=2000)
                db.insert_tool_run("note.add", status="skipped", timestamp_ms=3000)

                summary = db.get_tool_run_summary()

                self.assertEqual(summary["count"], 3)
                self.assertEqual(summary["success_count"], 1)
                self.assertEqual(summary["failed_count"], 1)
                self.assertEqual(summary["skipped_count"], 1)
                self.assertEqual(summary["latest_tool"], "note.add")
                self.assertEqual(summary["tool_count"]["robot.say"], 2)
                self.assertEqual(summary["status_count"]["skipped"], 1)

    def test_empty_tool_run_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                summary = db.get_tool_run_summary()

                self.assertEqual(summary["count"], 0)
                self.assertEqual(summary["success_count"], 0)
                self.assertEqual(summary["failed_count"], 0)
                self.assertEqual(summary["skipped_count"], 0)
                self.assertIsNone(summary["latest_tool"])


if __name__ == "__main__":
    unittest.main()
