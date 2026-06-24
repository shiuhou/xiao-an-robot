"""Integration tests for POST /api/context/preview."""

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


class ApiContextPreviewIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "api-context.db"
        self.runtime = ApiRuntime(
            db_path=str(db_path),
            robot_ws_url="ws://127.0.0.1:65534/agent",
        )
        self.runtime.memory_store.insert_task(title="完成 Step 28.2")
        self.runtime.memory_store.insert_note(content="API context preview note")
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

    def post_json(self, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"{self.base_url}/api/context/preview",
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

    def test_task_question_returns_project_memory_without_writing_events(self) -> None:
        before_count = len(
            self.runtime.memory_store.query_recent_events(limit=100),
        )

        status, body = self.post_json({
            "text": "我还有哪些任务没完成？",
            "session_id": "preview-session",
        })

        after_count = len(
            self.runtime.memory_store.query_recent_events(limit=100),
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        data = body["data"]
        self.assertEqual(data["session_id"], "preview-session")
        self.assertIn("tasks", data["requested_scopes"])
        self.assertEqual(
            data["context"]["project_memory"]["recent_tasks"][0]["title"],
            "完成 Step 28.2",
        )
        self.assertEqual(before_count, after_count)

    def test_note_question_returns_note_context(self) -> None:
        status, body = self.post_json({
            "text": "我刚才让你记了什么？",
        })

        self.assertEqual(status, 200)
        self.assertIn("notes", body["data"]["requested_scopes"])
        self.assertEqual(
            body["data"]["context"]["project_memory"]["recent_notes"][0][
                "content"
            ],
            "API context preview note",
        )

    def test_casual_question_does_not_inject_project_memory(self) -> None:
        status, body = self.post_json({"text": "你好小安"})

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["requested_scopes"], [])
        context = body["data"]["context"]
        self.assertNotIn("project_memory", context)
        for key in (
            "recent_notes",
            "recent_tasks",
            "recent_reminders",
            "recent_summaries",
            "recent_tool_runs",
        ):
            self.assertNotIn(key, context)

    def test_missing_text_returns_missing_text(self) -> None:
        status, body = self.post_json({})

        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "missing_text")


if __name__ == "__main__":
    unittest.main()
