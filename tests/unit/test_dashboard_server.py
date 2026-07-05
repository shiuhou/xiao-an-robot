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
    load_openclaw_dashboard_today,
    load_today_data,
    parse_args,
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
        self.assertEqual(state["voice"]["status"], "idle")
        self.assertEqual(state["voice"]["transcript"], "")

    def test_state_includes_demo1_voice_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "demo1_transcript.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "transcript": "帮我记一下今晚八点修改报告第三章",
                        "source": "asr",
                        "timestamp": "2026-07-03T02:54:00",
                        "audio_device": "UACDemoV1.0: USB Audio",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            state = load_dashboard_state(data_dir=data_dir, runtime_dir=data_dir)

        self.assertEqual(state["voice"]["status"], "done")
        self.assertEqual(state["voice"]["source"], "asr")
        self.assertEqual(state["voice"]["transcript"], "帮我记一下今晚八点修改报告第三章")
        self.assertEqual(state["voice"]["audio_device"], "UACDemoV1.0: USB Audio")

    def test_state_includes_assistant_capture_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "assistant_capture_result.json").write_text(
                json.dumps(
                    {
                        "status": "needs_clarification",
                        "transcript": "帮我记一下，下星期有会议",
                        "reply_text": "需要告诉我具体哪一天和几点。",
                        "source_of_truth": "openclaw_xiaoan_runtime",
                        "capture": {
                            "status": "needs_clarification",
                            "kind": "meeting",
                            "title": "下星期有会议",
                            "missing_fields": ["date", "time"],
                            "source_of_truth": "openclaw_xiaoan_runtime",
                        },
                        "feedback": {
                            "ok": True,
                            "actions": [],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            state = load_dashboard_state(data_dir=data_dir, runtime_dir=data_dir)

        self.assertEqual(state["assistant_capture"]["status"], "needs_clarification")
        self.assertEqual(state["assistant_capture"]["capture"]["kind"], "meeting")
        self.assertEqual(
            state["assistant_capture"]["source_of_truth"],
            "openclaw_xiaoan_runtime",
        )


class DashboardTodayDataTest(unittest.TestCase):
    def _write_today_fallback(self, data_dir: Path) -> None:
        (data_dir / "today.json").write_text(
            json.dumps(
                {
                    "schedules": [{"title": "fallback schedule"}],
                    "todos": [{"title": "fallback todo"}],
                    "alarms": [{"title": "fallback alarm"}],
                }
            ),
            encoding="utf-8",
        )

    def _write_runtime_dashboard(
        self,
        workspace: Path,
        payload: dict[str, object] | str,
    ) -> None:
        dashboard_path = workspace / "state" / "dashboard.json"
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            dashboard_path.write_text(payload, encoding="utf-8")
        else:
            dashboard_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_today_data_prefers_valid_openclaw_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as data_temp, tempfile.TemporaryDirectory() as workspace_temp:
            data_dir = Path(data_temp)
            workspace = Path(workspace_temp)
            self._write_today_fallback(data_dir)
            self._write_runtime_dashboard(
                workspace,
                {
                    "schema": "xiaoan.dashboard.v1",
                    "schedules": [{"title": "runtime schedule"}],
                    "todos": [{"title": "runtime todo"}],
                    "reminders": [{"title": "runtime reminder"}],
                },
            )

            today = load_today_data(data_dir, openclaw_workspace=workspace)

        self.assertEqual(today["schedules"], [{"title": "runtime schedule"}])
        self.assertEqual(today["todos"], [{"title": "runtime todo"}])
        self.assertEqual(today["alarms"], [{"title": "runtime reminder"}])

    def test_today_data_falls_back_when_openclaw_dashboard_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as data_temp, tempfile.TemporaryDirectory() as workspace_temp:
            data_dir = Path(data_temp)
            workspace = Path(workspace_temp)
            self._write_today_fallback(data_dir)

            today = load_today_data(data_dir, openclaw_workspace=workspace)

        self.assertEqual(today["todos"], [{"title": "fallback todo"}])

    def test_today_data_falls_back_when_openclaw_dashboard_is_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as data_temp, tempfile.TemporaryDirectory() as workspace_temp:
            data_dir = Path(data_temp)
            workspace = Path(workspace_temp)
            self._write_today_fallback(data_dir)
            self._write_runtime_dashboard(workspace, "{invalid")

            today = load_today_data(data_dir, openclaw_workspace=workspace)

        self.assertEqual(today["alarms"], [{"title": "fallback alarm"}])

    def test_today_data_falls_back_when_openclaw_schema_is_wrong(self) -> None:
        with tempfile.TemporaryDirectory() as data_temp, tempfile.TemporaryDirectory() as workspace_temp:
            data_dir = Path(data_temp)
            workspace = Path(workspace_temp)
            self._write_today_fallback(data_dir)
            self._write_runtime_dashboard(
                workspace,
                {
                    "schema": "other.schema",
                    "todos": [{"title": "runtime todo"}],
                },
            )

            today = load_today_data(data_dir, openclaw_workspace=workspace)

        self.assertEqual(today["schedules"], [{"title": "fallback schedule"}])

    def test_openclaw_dashboard_maps_reminders_to_alarms(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_temp:
            workspace = Path(workspace_temp)
            self._write_runtime_dashboard(
                workspace,
                {
                    "schema": "xiaoan.dashboard.v1",
                    "schedules": [],
                    "todos": [],
                    "reminders": [{"title": "drink water"}],
                },
            )

            today = load_openclaw_dashboard_today(workspace)

        self.assertIsNotNone(today)
        assert today is not None
        self.assertEqual(today["alarms"], [{"title": "drink water"}])

    def test_parse_args_accepts_openclaw_workspace(self) -> None:
        args = parse_args(["--openclaw-workspace", "/tmp/xiaoan-runtime"])

        self.assertEqual(args.openclaw_workspace, "/tmp/xiaoan-runtime")

    def test_dashboard_state_includes_openclaw_dashboard_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as data_temp, tempfile.TemporaryDirectory() as workspace_temp:
            data_dir = Path(data_temp)
            workspace = Path(workspace_temp)
            self._write_runtime_dashboard(
                workspace,
                {
                    "schema": "xiaoan.dashboard.v1",
                    "mode": "focus",
                    "status_text": "正在专注",
                    "next_item": {"title": "写报告"},
                    "latest_reply": {"display_text": "我帮你看着今天的重点。"},
                    "todos": [],
                    "schedules": [],
                    "reminders": [],
                },
            )

            state = load_dashboard_state(
                data_dir=data_dir,
                runtime_dir=data_dir,
                openclaw_workspace=workspace,
            )

        self.assertEqual(state["openclaw_dashboard"]["mode"], "focus")
        self.assertEqual(
            state["openclaw_dashboard"]["latest_reply"]["display_text"],
            "我帮你看着今天的重点。",
        )


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

        self.assertIn("Todo List", html)
        self.assertIn("今日日程", html)
        self.assertEqual(state["pipeline"]["robot"], "ready")
        self.assertEqual(state["triggers"][0]["title"], "喝水提醒")


class DashboardStaticAssetTest(unittest.TestCase):
    def test_dashboard_defaults_to_work_assistant_layout(self) -> None:
        html = (DEFAULT_STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")
        css = (DEFAULT_STATIC_DIR / "dashboard.css").read_text(encoding="utf-8")

        self.assertIn('class="todo-panel"', html)
        self.assertIn('class="schedule-panel"', html)
        self.assertIn('id="nextLine"', html)
        self.assertIn('id="replyLine"', html)
        self.assertIn(
            "grid-template-areas:",
            css,
        )
        self.assertIn('"todos schedules"', css)
        self.assertIn("font-size: 74px;", css)
        self.assertIn("background: #eef2f0;", css)

    def test_static_assets_focus_on_today_work_data(self) -> None:
        css = (DEFAULT_STATIC_DIR / "dashboard.css").read_text(encoding="utf-8")
        js = (DEFAULT_STATIC_DIR / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("renderTodos", js)
        self.assertIn("renderSchedules", js)
        self.assertIn("openclaw_dashboard", js)
        self.assertIn("latest_reply", js)
        self.assertIn(".todo-item", css)
        self.assertIn(".schedule-item", css)


if __name__ == "__main__":
    unittest.main()
