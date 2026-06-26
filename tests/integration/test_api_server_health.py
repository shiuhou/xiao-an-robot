"""Integration tests for the standard-library local API server."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from base_station.api.runtime import ApiRuntime
from base_station.api.server import create_server


class ApiServerHealthIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "api.db"
        self.runtime = ApiRuntime(
            db_path=str(db_path),
            robot_ws_url="ws://127.0.0.1:65534/agent",
        )
        self.server = create_server(
            host="127.0.0.1",
            port=0,
            runtime=self.runtime,
        )
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

    def get_json(self, path: str) -> tuple[int, dict, object]:
        with urllib.request.urlopen(
            f"{self.base_url}{path}",
            timeout=5,
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body, response.headers

    def test_health_and_status_without_external_services(self) -> None:
        health_status, health, health_headers = self.get_json("/api/health")
        status_code, status, _ = self.get_json("/api/status")

        self.assertEqual(health_status, 200)
        self.assertTrue(health["ok"])
        self.assertEqual(health["data"]["status"], "ok")
        self.assertEqual(
            health_headers["Content-Type"],
            "application/json; charset=utf-8",
        )
        self.assertEqual(health_headers["Access-Control-Allow-Origin"], "*")

        self.assertEqual(status_code, 200)
        self.assertTrue(status["ok"])
        self.assertEqual(status["data"]["status"], "ready")
        self.assertEqual(
            status["data"]["robot_ws_url"],
            "ws://127.0.0.1:65534/agent",
        )
        self.assertTrue(status["data"]["components"]["brain"])
        self.assertTrue(status["data"]["components"]["memory_store"])
        self.assertEqual(status["data"]["storage_role"], "local_event_store")
        self.assertEqual(status["data"]["openclaw_backend"], "fake")
        self.assertEqual(status["data"]["openclaw_agent"], "xiaoan-runtime")
        self.assertEqual(
            status["data"]["robot_connection_status"],
            "unknown_until_command_ack",
        )
        self.assertEqual(
            status["data"]["robot_connection_detail"]["last_tool"],
            None,
        )
        self.assertIn(
            "long_term_memory",
            status["data"]["openclaw_owned_features"],
        )
        self.assertIn(
            "robot_action_execution",
            status["data"]["xiao_an_robot_owned_features"],
        )
        deprecated = {
            item["name"]: item["status"]
            for item in status["data"]["deprecated_local_features"]
        }
        self.assertEqual(deprecated["screen_monitoring"], "deprecated")
        self.assertEqual(deprecated["tasks"], "legacy_compatibility")


if __name__ == "__main__":
    unittest.main()
