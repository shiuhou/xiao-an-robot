"""Integration tests for the local tool-call HTTP API."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from base_station.api.runtime import ApiRuntime
from base_station.api.server import create_server


class ApiToolsIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "api-tools.db"
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

    def get_json(self, path: str) -> tuple[int, dict]:
        with urllib.request.urlopen(
            f"{self.base_url}{path}",
            timeout=5,
        ) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post_json(self, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"{self.base_url}/api/tools/call",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return (
                    response.status,
                    json.loads(response.read().decode("utf-8")),
                )
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def call_tool(
        self,
        tool: str,
        arguments: dict | None = None,
        session_id: str = "api-tools-test",
    ) -> dict:
        status, body = self.post_json({
            "tool": tool,
            "arguments": arguments or {},
            "session_id": session_id,
        })
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        return body["data"]

    def test_list_tools_uses_executor_tool_names(self) -> None:
        status, body = self.get_json("/api/tools")

        self.assertEqual(status, 200)
        names = {item["name"] for item in body["data"]["tools"]}
        self.assertEqual(
            names,
            set(self.runtime.action_executor.LOCAL_TOOL_NAMES),
        )
        self.assertIn("note.add", names)
        self.assertIn("task.add", names)
        self.assertIn("reminder.add", names)

    def test_note_add_and_search_persist_full_memory_flow(self) -> None:
        add = self.call_tool(
            "note.add",
            {"content": "API release report"},
            session_id="note-session",
        )
        search = self.call_tool(
            "note.search",
            {"keyword": "release"},
        )

        self.assertEqual(
            add["result"]["executed_actions"][0]["name"],
            "note.add",
        )
        search_result = search["result"]["executed_actions"][0]["result"]
        self.assertEqual(search_result["items"][0]["content"], "API release report")
        note = self.runtime.memory_store.query_recent_notes()[0]
        self.assertEqual(note["content"], "API release report")
        note_event = self.runtime.memory_store.query_recent_events(
            event_type="note.add",
        )[0]
        self.assertEqual(note_event["session_id"], "note-session")
        runs = self.runtime.memory_store.query_recent_tool_runs(limit=10)
        statuses = {
            run["tool_name"]: run["status"]
            for run in runs
        }
        self.assertEqual(statuses["note.add"], "success")
        self.assertEqual(statuses["note.search"], "success")

    def test_task_add_and_query(self) -> None:
        self.call_tool("task.add", {"title": "finish API tools"})
        query = self.call_tool("task.query")

        tasks = query["result"]["executed_actions"][0]["result"]["tasks"]
        self.assertEqual(tasks[0]["title"], "finish API tools")
        self.assertEqual(
            self.runtime.memory_store.query_recent_tool_runs(
                tool_name="task.add",
            )[0]["status"],
            "success",
        )
        self.assertEqual(
            self.runtime.memory_store.query_recent_tool_runs(
                tool_name="task.query",
            )[0]["status"],
            "success",
        )

    def test_reminder_add_and_query(self) -> None:
        self.call_tool(
            "reminder.add",
            {"message": "review API", "delay_seconds": 60},
        )
        query = self.call_tool("reminder.query")

        reminders = query["result"]["executed_actions"][0]["result"][
            "reminders"
        ]
        self.assertEqual(reminders[0]["message"], "review API")
        self.assertEqual(
            self.runtime.memory_store.query_recent_tool_runs(
                tool_name="reminder.add",
            )[0]["status"],
            "success",
        )
        self.assertEqual(
            self.runtime.memory_store.query_recent_tool_runs(
                tool_name="reminder.query",
            )[0]["status"],
            "success",
        )

    def test_unknown_tool_returns_failure_result_and_records_failed_run(self) -> None:
        data = self.call_tool("unknown.tool", {"text": "test failure"})

        result = data["result"]
        self.assertEqual(result["executed_actions"], [])
        self.assertEqual(result["skipped_actions"][0]["reason"], "unknown_tool")
        run = self.runtime.memory_store.query_recent_tool_runs(
            tool_name="unknown.tool",
        )[0]
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "unknown_tool")
        event = next(
            item
            for item in self.runtime.memory_store.query_recent_events(
                event_type="tool.run",
            )
            if item["payload"].get("tool_name") == "unknown.tool"
        )
        self.assertEqual(event["payload"]["error"], "unknown_tool")

    def test_missing_tool_and_invalid_arguments(self) -> None:
        missing_status, missing = self.post_json({"arguments": {}})
        invalid_status, invalid = self.post_json({
            "tool": "note.add",
            "arguments": "not-an-object",
        })

        self.assertEqual(missing_status, 400)
        self.assertEqual(missing["error"]["code"], "missing_tool")
        self.assertEqual(invalid_status, 400)
        self.assertEqual(invalid["error"]["code"], "invalid_arguments")


if __name__ == "__main__":
    unittest.main()
