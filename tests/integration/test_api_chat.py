"""Integration tests for POST /api/chat."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from agent.core.openclaw_adapter import OpenClawDecision
from base_station.api.runtime import ApiRuntime
from base_station.api.server import create_server


class ApiChatIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "api-chat.db"
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

    def post_json(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
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

    def test_chat_returns_brain_result(self) -> None:
        status, body = self.post_json(
            "/api/chat",
            {
                "text": "你好小安",
                "session_id": "chat-session",
                "metadata": {"source": "integration-test"},
            },
        )

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["route"], "frontend_openclaw")
        event = self.runtime.brain.openclaw_adapter.events[-1]
        self.assertEqual(event.session_id, "chat-session")
        self.assertEqual(
            event.context["payload"]["metadata"],
            {"source": "integration-test"},
        )

    def test_chat_missing_and_empty_text_return_missing_text(self) -> None:
        for payload in ({}, {"text": ""}, {"text": "   "}, {"text": 123}):
            with self.subTest(payload=payload):
                status, body = self.post_json("/api/chat", payload)
                self.assertEqual(status, 400)
                self.assertFalse(body["ok"])
                self.assertEqual(body["error"]["code"], "missing_text")

    def test_chat_defaults_session_id(self) -> None:
        status, body = self.post_json("/api/chat", {"text": "随便聊聊"})

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(
            self.runtime.brain.openclaw_adapter.events[-1].session_id,
            "default",
        )

    def test_chat_reply_text_keeps_200_when_robot_is_offline(self) -> None:
        self.runtime.brain.openclaw_adapter.decision = OpenClawDecision(
            handled=True,
            reply_text="frontend reply",
        )

        status, body = self.post_json(
            "/api/chat",
            {
                "text": "你好小安",
                "session_id": "offline-reply",
            },
        )

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"], body)
        result = body["data"]
        self.assertEqual(result["reply_text"], "frontend reply")
        self.assertEqual(result["executed_actions"], [])
        self.assertEqual(result["skipped_actions"][0]["name"], "robot.say")
        self.assertEqual(
            result["skipped_actions"][0]["reason"],
            "robot_action_failed",
        )
        self.assertIn(
            "Failed to connect",
            result["skipped_actions"][0]["result"]["error"],
        )
        runs = self.runtime.memory_store.query_recent_tool_runs(limit=5)
        self.assertEqual(runs[0]["tool_name"], "robot.say")
        self.assertEqual(runs[0]["status"], "failed")
        self.assertIn("Failed to connect", runs[0]["error"])


if __name__ == "__main__":
    unittest.main()
