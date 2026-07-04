from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    import websockets  # noqa: F401
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None

if websockets is not None:
    from base_station.ws_server import server as ws_server
else:  # pragma: no cover
    ws_server = None


@unittest.skipIf(websockets is None, "websockets dependency is not installed")
class WebSocketStateSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        ws_server.reset_state_for_tests()

    def tearDown(self) -> None:
        ws_server.reset_state_for_tests()

    def test_writer_uses_replaceable_tmp_and_outputs_parseable_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            ws_server.sessions["robot-1"] = {
                "device_id": "robot-1",
                "session_id": "sess-1",
                "last_hb": 123.0,
                "battery": 88,
                "ip": "192.168.1.50",
                "wifi_rssi": -52,
            }
            ok = ws_server.write_ws_state_snapshot(runtime)

            self.assertTrue(ok)
            path = runtime / "ws_state.json"
            self.assertTrue(path.exists())
            self.assertFalse((runtime / "ws_state.json.tmp").exists())
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("updated_at", data)
        self.assertEqual(data["online_devices"], ["robot-1"])
        self.assertEqual(data["sessions"]["robot-1"]["battery"], 88)
        self.assertNotIn("ws", data["sessions"]["robot-1"])

    def test_record_ws_event_updates_last_ack_and_counters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_runtime = ws_server.ws_runtime_dir
            ws_server.ws_runtime_dir = Path(temp_dir)
            try:
                ws_server.record_ws_event(
                    "command.ack",
                    {"command_type": "display.expression", "status": "ok"},
                    device_id="robot-1",
                )
                data = json.loads((Path(temp_dir) / "ws_state.json").read_text(encoding="utf-8"))
            finally:
                ws_server.ws_runtime_dir = original_runtime

        self.assertEqual(data["last_command_ack"]["payload"]["command_type"], "display.expression")
        self.assertEqual(data["counters"]["control_messages"], 1)


if __name__ == "__main__":
    unittest.main()
