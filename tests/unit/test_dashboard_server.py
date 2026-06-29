"""Tests for the standalone Dock dashboard server."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from base_station.dashboard.dashboard_server import (
    DEFAULT_STATIC_DIR,
    create_server,
    load_dashboard_state,
)


class DashboardStateTest(unittest.TestCase):
    def test_state_includes_pipeline_and_caps_recent_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "triggers.json").write_text(
                json.dumps(
                    {
                        "pipeline": {
                            "current_state": "processing",
                            "robot": "ready",
                            "base_station": "ready",
                            "agent": "running",
                            "action": "waiting",
                        },
                        "triggers": [
                            {
                                "time": "14:30",
                                "source": "alarm",
                                "title": "喝水提醒",
                                "chain": "Alarm → Agent → Robot Voice",
                                "status": "completed",
                                "detail": "已播放休息提醒",
                            },
                            {
                                "time": "14:05",
                                "source": "emotion",
                                "title": "疲勞關懷",
                                "chain": "Camera → Emotion → VLM → Agent → Robot",
                                "status": "processing",
                                "detail": "正在生成關懷回應",
                            },
                            {
                                "time": "13:50",
                                "source": "manual",
                                "title": "表情測試",
                                "chain": "Dashboard → Agent Command → Robot Display",
                                "status": "acked",
                                "detail": "Robot 已確認表情切換",
                            },
                            {
                                "time": "13:20",
                                "source": "system",
                                "title": "多餘記錄",
                                "chain": "System → Dashboard",
                                "status": "completed",
                                "detail": "不應顯示",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            state = load_dashboard_state(data_dir=data_dir, runtime_dir=data_dir)

        self.assertIn("pipeline", state)
        self.assertEqual(state["pipeline"]["current_state"], "processing")
        self.assertEqual(state["pipeline"]["agent"], "running")
        self.assertIn("last_updated_at", state["pipeline"])
        self.assertEqual(len(state["triggers"]), 3)
        self.assertEqual(
            [item["source"] for item in state["triggers"]],
            ["alarm", "emotion", "manual"],
        )

    def test_state_uses_safe_defaults_when_trigger_mock_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)

            state = load_dashboard_state(data_dir=data_dir, runtime_dir=data_dir)

        self.assertEqual(state["pipeline"]["current_state"], "idle")
        self.assertEqual(state["pipeline"]["robot"], "unknown")
        self.assertEqual(state["pipeline"]["base_station"], "ready")
        self.assertEqual(state["pipeline"]["agent"], "unknown")
        self.assertEqual(state["pipeline"]["action"], "waiting")
        self.assertEqual(state["triggers"], [])


class DashboardHttpTest(unittest.TestCase):
    def test_dashboard_routes_return_html_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "triggers.json").write_text(
                json.dumps(
                    {
                        "pipeline": {"robot": "ready"},
                        "triggers": [
                            {
                                "time": "14:30",
                                "source": "alarm",
                                "title": "喝水提醒",
                                "chain": "Alarm → Agent → Robot Voice",
                                "status": "completed",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            server = create_server(
                "127.0.0.1",
                0,
                data_dir=data_dir,
                runtime_dir=data_dir,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            base_url = f"http://{host}:{port}"
            try:
                with urllib.request.urlopen(f"{base_url}/dashboard", timeout=5) as response:
                    html = response.read().decode("utf-8")
                with urllib.request.urlopen(
                    f"{base_url}/api/dashboard/state",
                    timeout=5,
                ) as response:
                    state = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertIn("最近觸發", html)
        self.assertEqual(state["pipeline"]["robot"], "ready")
        self.assertEqual(state["triggers"][0]["title"], "喝水提醒")


class DashboardStaticAssetTest(unittest.TestCase):
    def test_today_schedule_is_the_primary_left_panel(self) -> None:
        html = (DEFAULT_STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")
        css = (DEFAULT_STATIC_DIR / "dashboard.css").read_text(encoding="utf-8")

        self.assertLess(
            html.index('class="today-band"'),
            html.index('class="focus-band"'),
        )
        self.assertIn(
            "grid-template-rows: 132px minmax(0, 1fr) 150px;",
            css,
        )

    def test_static_assets_keep_signal_grid_and_trigger_status_visible(self) -> None:
        css = (DEFAULT_STATIC_DIR / "dashboard.css").read_text(encoding="utf-8")
        js = (DEFAULT_STATIC_DIR / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn(
            "grid-template-rows: repeat(3, minmax(0, 1fr));",
            css,
        )
        self.assertIn("trigger-chain", js)
        self.assertIn("trigger-status", js)
        self.assertIn(".trigger-status", css)


if __name__ == "__main__":
    unittest.main()
