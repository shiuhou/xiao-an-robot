"""Integration tests for read-only memory and project-context APIs."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from base_station.api.runtime import ApiRuntime
from base_station.api.server import create_server


class ApiMemoryIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "api-memory.db"
        self.runtime = ApiRuntime(
            db_path=str(db_path),
            robot_ws_url="ws://127.0.0.1:65534/agent",
        )
        self._seed_memory()
        self.server = create_server("127.0.0.1", 0, self.runtime)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.runtime.close()
        self.temp_dir.cleanup()

    def _seed_memory(self) -> None:
        self.runtime.call_tool(
            "note.add",
            {"content": "release report note"},
        )
        self.runtime.call_tool(
            "work_context.record",
            {
                "content": "implement Step 28 memory API",
                "app_name": "VS Code",
            },
        )
        self.runtime.call_tool(
            "summary.daily",
            {"date": "2026-06-22"},
        )
        task_add = self.runtime.call_tool(
            "task.add",
            {"title": "completed API task"},
        )
        task_id = task_add["result"]["executed_actions"][0]["result"]["result"][
            "task_result"
        ]["task_id"]
        self.runtime.call_tool("task.complete", {"task_id": task_id})
        reminder_add = self.runtime.call_tool(
            "reminder.add",
            {"message": "fired API reminder", "delay_seconds": 60},
        )
        reminder_id = reminder_add["result"]["executed_actions"][0]["result"][
            "result"
        ]["reminder_result"]["reminder_id"]
        self.runtime.memory_store.mark_reminder_fired(reminder_id)

    def get_json(
        self,
        path: str,
        params: dict[str, object] | None = None,
    ) -> tuple[int, dict]:
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_read_only_memory_endpoints(self) -> None:
        before_events = len(
            self.runtime.memory_store.query_recent_events(limit=200),
        )
        before_runs = len(
            self.runtime.memory_store.query_recent_tool_runs(limit=200),
        )

        _, memory = self.get_json(
            "/api/memory/recent",
            {"event_type": "note.add", "limit": 10},
        )
        _, notes = self.get_json(
            "/api/notes",
            {"q": "release", "limit": 10},
        )
        _, work = self.get_json(
            "/api/work-activities",
            {"query": "Step 28", "limit": 10},
        )
        _, summaries = self.get_json(
            "/api/summaries",
            {"summary_type": "daily", "date": "2026-06-22"},
        )
        _, tool_runs = self.get_json(
            "/api/tool-runs",
            {"tool_name": "note.add", "status": "success"},
        )
        _, tasks = self.get_json(
            "/api/tasks",
            {"include_done": "true"},
        )
        _, reminders = self.get_json(
            "/api/reminders",
            {"include_fired": "true"},
        )
        _, project = self.get_json(
            "/api/project/context",
            {"scope": "notes", "limit": 5},
        )

        self.assertEqual(memory["data"]["events"][0]["event_type"], "note.add")
        self.assertEqual(
            notes["data"]["notes"][0]["content"],
            "release report note",
        )
        self.assertEqual(
            work["data"]["work_activities"][0]["app_name"],
            "VS Code",
        )
        summary = summaries["data"]["summaries"][0]
        self.assertEqual(summary["summary_type"], "daily")
        self.assertIn("content_preview", summary)
        self.assertNotIn("content", summary)
        self.assertEqual(tool_runs["data"]["tool_runs"][0]["tool_name"], "note.add")
        self.assertEqual(tool_runs["data"]["tool_runs"][0]["status"], "success")
        self.assertEqual(tasks["data"]["tasks"][0]["status"], "done")
        self.assertEqual(reminders["data"]["reminders"][0]["status"], "fired")
        self.assertEqual(project["data"]["scope"], "notes")
        self.assertEqual(
            project["data"]["recent_notes"][0]["content"],
            "release report note",
        )

        after_events = len(
            self.runtime.memory_store.query_recent_events(limit=200),
        )
        after_runs = len(
            self.runtime.memory_store.query_recent_tool_runs(limit=200),
        )
        self.assertEqual(before_events, after_events)
        self.assertEqual(before_runs, after_runs)

    def test_invalid_limit_uses_default_and_boolean_aliases_are_supported(self) -> None:
        _, notes = self.get_json("/api/notes", {"limit": "invalid"})
        _, tasks = self.get_json("/api/tasks", {"include_done": "yes"})
        _, reminders = self.get_json(
            "/api/reminders",
            {"include_fired": "1"},
        )
        _, pending_only = self.get_json(
            "/api/tasks",
            {"include_done": "no"},
        )

        self.assertTrue(notes["ok"])
        self.assertEqual(tasks["data"]["tasks"][0]["status"], "done")
        self.assertEqual(reminders["data"]["reminders"][0]["status"], "fired")
        self.assertEqual(pending_only["data"]["tasks"], [])


if __name__ == "__main__":
    unittest.main()
