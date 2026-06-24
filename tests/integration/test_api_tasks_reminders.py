"""Integration tests for dedicated task and reminder write APIs."""

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


class ApiTasksRemindersIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "api-tasks-reminders.db"
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

    @staticmethod
    def _tool_item_id(data: dict, result_key: str, id_key: str) -> int:
        action_result = data["result"]["executed_actions"][0]["result"]
        return action_result["result"][result_key][id_key]

    def test_task_create_complete_cancel_and_validation(self) -> None:
        create_status, created = self.request_json(
            "POST",
            "/api/tasks",
            {
                "title": "finish Step 28.5",
                "description": "dedicated task API",
                "priority": "high",
            },
        )
        task_id = self._tool_item_id(
            created["data"],
            "task_result",
            "task_id",
        )
        _, listed = self.request_json("GET", "/api/tasks")
        complete_status, completed = self.request_json(
            "POST",
            f"/api/tasks/{task_id}/complete",
        )

        _, second = self.request_json(
            "POST",
            "/api/tasks",
            {"title": "cancel this task"},
        )
        second_id = self._tool_item_id(
            second["data"],
            "task_result",
            "task_id",
        )
        cancel_status, cancelled = self.request_json(
            "POST",
            f"/api/tasks/{second_id}/cancel",
        )
        invalid_status, invalid = self.request_json(
            "POST",
            "/api/tasks/not-an-id/complete",
        )
        missing_status, missing = self.request_json(
            "POST",
            "/api/tasks",
            {"title": "  "},
        )

        self.assertEqual(create_status, 200)
        self.assertEqual(listed["data"]["tasks"][0]["title"], "finish Step 28.5")
        self.assertEqual(complete_status, 200)
        self.assertTrue(completed["ok"])
        self.assertEqual(cancel_status, 200)
        self.assertTrue(cancelled["ok"])
        all_tasks = self.runtime.memory_store.query_tasks(include_done=True)
        statuses = {item["id"]: item["status"] for item in all_tasks}
        self.assertEqual(statuses[task_id], "done")
        self.assertEqual(statuses[second_id], "cancelled")
        self.assertEqual(invalid_status, 400)
        self.assertEqual(invalid["error"]["code"], "invalid_id")
        self.assertEqual(missing_status, 400)
        self.assertEqual(missing["error"]["code"], "missing_title")

    def test_task_not_found_returns_404_and_records_failed_tool_run(self) -> None:
        status, body = self.request_json(
            "POST",
            "/api/tasks/999999/complete",
        )

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "task_not_found")
        run = self.runtime.memory_store.query_recent_tool_runs(
            tool_name="task.complete",
        )[0]
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "task_not_found")

    def test_reminder_create_due_mark_fired_cancel_and_validation(self) -> None:
        due_at_ms = int(time.time() * 1000) - 1
        create_status, created = self.request_json(
            "POST",
            "/api/reminders",
            {
                "message": "run the due reminder test",
                "due_at_ms": due_at_ms,
            },
        )
        reminder_id = self._tool_item_id(
            created["data"],
            "reminder_result",
            "reminder_id",
        )
        _, listed = self.request_json("GET", "/api/reminders")
        _, due = self.request_json("GET", "/api/reminders/due")
        fired_status, fired = self.request_json(
            "POST",
            f"/api/reminders/{reminder_id}/mark-fired",
        )

        _, second = self.request_json(
            "POST",
            "/api/reminders",
            {"message": "cancel this reminder", "delay_seconds": 60},
        )
        second_id = self._tool_item_id(
            second["data"],
            "reminder_result",
            "reminder_id",
        )
        cancel_status, cancelled = self.request_json(
            "POST",
            f"/api/reminders/{second_id}/cancel",
        )
        invalid_status, invalid = self.request_json(
            "POST",
            "/api/reminders/bad-id/cancel",
        )
        missing_status, missing = self.request_json(
            "POST",
            "/api/reminders",
            {"message": ""},
        )
        delay_status, invalid_delay = self.request_json(
            "POST",
            "/api/reminders",
            {"message": "bad delay", "delay_seconds": "soon"},
        )
        time_status, missing_time = self.request_json(
            "POST",
            "/api/reminders",
            {"message": "missing schedule"},
        )

        self.assertEqual(create_status, 200)
        self.assertEqual(
            listed["data"]["reminders"][0]["message"],
            "run the due reminder test",
        )
        self.assertEqual(due["data"]["reminders"][0]["id"], reminder_id)
        self.assertEqual(fired_status, 200)
        self.assertTrue(fired["data"]["ok"])
        self.assertEqual(cancel_status, 200)
        self.assertTrue(cancelled["ok"])
        all_reminders = self.runtime.memory_store.query_reminders(
            include_fired=True,
        )
        statuses = {item["id"]: item["status"] for item in all_reminders}
        self.assertEqual(statuses[reminder_id], "fired")
        self.assertEqual(statuses[second_id], "cancelled")
        self.assertEqual(invalid_status, 400)
        self.assertEqual(invalid["error"]["code"], "invalid_id")
        self.assertEqual(missing_status, 400)
        self.assertEqual(missing["error"]["code"], "missing_message")
        self.assertEqual(delay_status, 400)
        self.assertEqual(
            invalid_delay["error"]["code"],
            "invalid_delay_seconds",
        )
        self.assertEqual(time_status, 400)
        self.assertEqual(
            missing_time["error"]["code"],
            "missing_reminder_time",
        )
        fired_run = self.runtime.memory_store.query_recent_tool_runs(
            tool_name="reminder.mark_fired",
        )[0]
        self.assertEqual(fired_run["status"], "success")
        fired_events = self.runtime.memory_store.query_recent_events(
            event_type="reminder.fired",
        )
        self.assertEqual(fired_events[0]["payload"]["reminder_id"], reminder_id)

    def test_reminder_not_found_returns_404_and_records_failed_run(self) -> None:
        status, body = self.request_json(
            "POST",
            "/api/reminders/999999/cancel",
        )
        fired_status, fired = self.request_json(
            "POST",
            "/api/reminders/999999/mark-fired",
        )

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "reminder_not_found")
        self.assertEqual(fired_status, 404)
        self.assertEqual(fired["error"]["code"], "reminder_not_found")
        cancel_run = self.runtime.memory_store.query_recent_tool_runs(
            tool_name="reminder.cancel",
        )[0]
        fired_run = self.runtime.memory_store.query_recent_tool_runs(
            tool_name="reminder.mark_fired",
        )[0]
        self.assertEqual(cancel_run["status"], "failed")
        self.assertEqual(fired_run["status"], "failed")

    def test_write_endpoints_record_tool_runs_and_memory_events(self) -> None:
        _, task = self.request_json(
            "POST",
            "/api/tasks",
            {"title": "audit API writes"},
        )
        task_id = self._tool_item_id(task["data"], "task_result", "task_id")
        self.request_json("POST", f"/api/tasks/{task_id}/complete")
        _, reminder = self.request_json(
            "POST",
            "/api/reminders",
            {"message": "audit reminder writes", "delay_seconds": 60},
        )
        reminder_id = self._tool_item_id(
            reminder["data"],
            "reminder_result",
            "reminder_id",
        )
        self.request_json("POST", f"/api/reminders/{reminder_id}/cancel")

        runs = self.runtime.memory_store.query_recent_tool_runs(limit=20)
        run_status = {
            item["tool_name"]: item["status"]
            for item in runs
        }
        self.assertEqual(run_status["task.add"], "success")
        self.assertEqual(run_status["task.complete"], "success")
        self.assertEqual(run_status["reminder.add"], "success")
        self.assertEqual(run_status["reminder.cancel"], "success")
        self.assertNotIn("ok", runs[0])

        event_types = {
            item["event_type"]
            for item in self.runtime.memory_store.query_recent_events(limit=50)
        }
        self.assertIn("task.added", event_types)
        self.assertIn("task.completed", event_types)
        self.assertIn("reminder.added", event_types)
        self.assertIn("reminder.cancelled", event_types)
        self.assertIn("tool.run", event_types)


if __name__ == "__main__":
    unittest.main()
