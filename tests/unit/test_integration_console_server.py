from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from base_station.integration_console.console_server import (
    IntegrationConsoleApp,
    create_server,
    read_ws_state,
)


class IntegrationConsoleHttpTest(unittest.TestCase):
    def test_health_and_state_work_without_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server(
                "127.0.0.1",
                0,
                runtime_dir=temp_dir,
                ws_url="ws://127.0.0.1:8765/agent",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            base_url = f"http://{host}:{port}"
            try:
                with urllib.request.urlopen(f"{base_url}/api/health", timeout=5) as response:
                    health = json.loads(response.read().decode("utf-8"))
                with urllib.request.urlopen(f"{base_url}/api/state", timeout=5) as response:
                    state = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertTrue(health["ok"])
        self.assertFalse(health["ws_state_exists"])
        self.assertTrue(state["ok"])
        self.assertFalse(state["ws_server"]["ok"])
        self.assertFalse(state["robot"]["online"])
        self.assertIn("latest_image", state["media"])

    def test_latest_image_missing_returns_structured_404(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server("127.0.0.1", 0, runtime_dir=temp_dir)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(f"http://{host}:{port}/api/latest-image", timeout=5)
                payload = json.loads(raised.exception.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(raised.exception.code, 404)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "not_found")


class IntegrationConsoleCommandTest(unittest.TestCase):
    def test_robot_expression_payload_is_agent_command(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.send_expression({"expression": "happy", "duration_ms": 1500, "loop": False})

        self.assertTrue(result["ok"])
        self.assertEqual(sent[0]["command"], "display.expression")
        self.assertEqual(sent[0]["expression"], "happy")
        self.assertEqual(sent[0]["duration_ms"], 1500)

    def test_motion_payload_uses_safe_defaults_and_action_id(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.send_motion({
                "action": "move_out_of_dock",
                "params": {"speed": 0.9, "distance_cm": 99, "timeout_ms": 9999},
                "bench": False,
            })

        self.assertTrue(result["ok"])
        payload = sent[0]
        self.assertEqual(payload["command"], "motion.execute")
        self.assertEqual(payload["action"], "move_out_of_dock")
        self.assertEqual(payload["params"]["speed"], 0.56)
        self.assertEqual(payload["params"]["distance_cm"], 10.0)
        self.assertEqual(payload["timeout_ms"], 1200)
        self.assertTrue(payload["action_id"].startswith("console-"))

    def test_scenario_runs_steps_in_order(self) -> None:
        sent: list[str] = []

        def sender(payload: dict) -> dict:
            sent.append(payload["command"])
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.run_scenario({"scenario": "direct-smoke"})

        self.assertTrue(result["ok"])
        self.assertEqual(sent, ["display.expression", "display.expression", "audio.play_local"])
        self.assertEqual(
            [step["name"] for step in result["steps"]],
            ["expression:idle", "expression:happy", "local_sound:success_ding"],
        )

    def test_tool_runner_rejects_arbitrary_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            result = app.run_tool({"tool": "echo hacked && rm -rf /"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "tool_not_allowed")


class IntegrationConsoleStateReaderTest(unittest.TestCase):
    def test_read_ws_state_handles_missing_empty_and_bad_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            missing = read_ws_state(runtime)
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["reason"], "not_found")

            (runtime / "ws_state.json").write_text("", encoding="utf-8")
            empty = read_ws_state(runtime)
            self.assertFalse(empty["ok"])
            self.assertEqual(empty["reason"], "empty")

            (runtime / "ws_state.json").write_text("{bad", encoding="utf-8")
            bad = read_ws_state(runtime)
            self.assertFalse(bad["ok"])
            self.assertTrue(bad["reason"].startswith("bad_json"))


if __name__ == "__main__":
    unittest.main()
