"""End-to-end local HTTP API flow without external services."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from base_station.api.runtime import ApiRuntime
from base_station.api.server import create_server


class LocalApiFlowIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "local-api-flow.db"
        self.runtime = ApiRuntime(
            db_path=str(db_path),
            robot_ws_url="ws://127.0.0.1:65534/agent",
        )
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

    def request_json(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict[str, object] | None = None,
    ) -> tuple[int, dict]:
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return (
                    response.status,
                    json.loads(response.read().decode("utf-8")),
                )
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def assert_ok(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict[str, object] | None = None,
    ) -> dict:
        status, response = self.request_json(method, path, body, params)
        self.assertEqual(status, 200, response)
        self.assertTrue(response["ok"], response)
        self.assertIsNone(response["error"])
        return response["data"]

    @staticmethod
    def _tool_item_id(data: dict, result_key: str, id_key: str) -> int:
        action_result = data["result"]["executed_actions"][0]["result"]
        return action_result["result"][result_key][id_key]

    def test_complete_local_api_flow(self) -> None:
        health = self.assert_ok("GET", "/api/health")
        status = self.assert_ok("GET", "/api/status")
        self.assertEqual(health["status"], "ok")
        self.assertEqual(status["status"], "ready")

        chat = self.assert_ok(
            "POST",
            "/api/chat",
            {
                "text": "Hello Xiao An",
                "session_id": "local-api-flow",
            },
        )
        self.assertEqual(chat["route"], "frontend_openclaw")

        preview = self.assert_ok(
            "POST",
            "/api/context/preview",
            {
                "text": "What tasks are still pending?",
                "session_id": "local-api-flow",
            },
        )
        self.assertIn("tasks", preview["requested_scopes"])
        self.assertIn("project_memory", preview["context"])

        tools = self.assert_ok("GET", "/api/tools")
        tool_names = {item["name"] for item in tools["tools"]}
        self.assertTrue(
            {"note.add", "task.add", "reminder.add"}.issubset(tool_names),
        )

        note_add = self.assert_ok(
            "POST",
            "/api/tools/call",
            {
                "tool": "note.add",
                "arguments": {"content": "Local API flow note"},
                "session_id": "local-api-flow",
            },
        )
        self.assertEqual(
            note_add["result"]["executed_actions"][0]["name"],
            "note.add",
        )
        notes = self.assert_ok(
            "GET",
            "/api/notes",
            params={"q": "flow note"},
        )
        self.assertEqual(notes["notes"][0]["content"], "Local API flow note")

        task_create = self.assert_ok(
            "POST",
            "/api/tasks",
            {
                "title": "Complete local API flow",
                "priority": "high",
                "session_id": "local-api-flow",
            },
        )
        task_id = self._tool_item_id(
            task_create,
            "task_result",
            "task_id",
        )
        tasks = self.assert_ok("GET", "/api/tasks")
        self.assertEqual(tasks["tasks"][0]["id"], task_id)
        task_complete = self.assert_ok(
            "POST",
            f"/api/tasks/{task_id}/complete",
            {"session_id": "local-api-flow"},
        )
        self.assertEqual(
            task_complete["result"]["executed_actions"][0]["name"],
            "task.complete",
        )

        reminder_create = self.assert_ok(
            "POST",
            "/api/reminders",
            {
                "message": "Verify due reminder",
                "due_at_ms": int(time.time() * 1000) - 1,
                "session_id": "local-api-flow",
            },
        )
        reminder_id = self._tool_item_id(
            reminder_create,
            "reminder_result",
            "reminder_id",
        )
        reminders = self.assert_ok("GET", "/api/reminders")
        self.assertEqual(reminders["reminders"][0]["id"], reminder_id)
        due = self.assert_ok("GET", "/api/reminders/due")
        self.assertEqual(due["reminders"][0]["id"], reminder_id)
        fired = self.assert_ok(
            "POST",
            f"/api/reminders/{reminder_id}/mark-fired",
            {"session_id": "local-api-flow"},
        )
        self.assertTrue(fired["ok"])

        project_context = self.assert_ok(
            "GET",
            "/api/project/context",
            params={"scope": "notes", "limit": 5},
        )
        self.assertEqual(project_context["scope"], "notes")
        self.assertEqual(
            project_context["recent_notes"][0]["content"],
            "Local API flow note",
        )

        memory = self.assert_ok(
            "GET",
            "/api/memory/recent",
            params={"limit": 100},
        )
        event_types = {item["event_type"] for item in memory["events"]}
        self.assertIn("note.add", event_types)
        self.assertIn("task.added", event_types)
        self.assertIn("task.completed", event_types)
        self.assertIn("reminder.added", event_types)
        self.assertIn("reminder.fired", event_types)
        self.assertIn("tool.run", event_types)

        tool_runs = self.assert_ok(
            "GET",
            "/api/tool-runs",
            params={"limit": 100},
        )
        run_statuses = {
            item["tool_name"]: item["status"]
            for item in tool_runs["tool_runs"]
        }
        self.assertEqual(run_statuses["note.add"], "success")
        self.assertEqual(run_statuses["task.add"], "success")
        self.assertEqual(run_statuses["reminder.add"], "success")
        self.assertEqual(run_statuses["reminder.mark_fired"], "success")


if __name__ == "__main__":
    unittest.main()
