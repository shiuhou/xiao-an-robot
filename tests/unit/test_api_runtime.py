"""Unit tests for API runtime dashboard synchronization."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from base_station.api.runtime import ApiRuntime
from base_station.api.server import parse_args


class ApiRuntimeDashboardSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace-xiaoan-runtime"
        self.runtime = ApiRuntime(
            db_path=str(self.root / "api-runtime.db"),
            robot_ws_url="ws://127.0.0.1:65534/agent",
            openclaw_workspace=self.workspace,
        )

    def tearDown(self) -> None:
        self.runtime.close()
        self.temp_dir.cleanup()

    def read_dashboard(self) -> dict:
        return json.loads(
            self.runtime.openclaw_dashboard_path.read_text(encoding="utf-8")
        )

    def test_set_latest_reply_creates_dashboard_json(self) -> None:
        self.runtime._set_latest_reply(
            notification_type="generic.notify",
            display_text="显示内容",
            spoken_text="",
            reply_text="",
            tool_calls=[],
            metadata={},
            session_id="default",
            source="unit-test",
        )

        dashboard = self.read_dashboard()
        self.assertEqual(dashboard["schema"], "xiaoan.dashboard.v1")
        self.assertTrue(dashboard["updated_at"])
        self.assertEqual(dashboard["latest_reply"]["display_text"], "显示内容")
        self.assertEqual(dashboard["latest_reply"]["source"], "unit-test")

    def test_notify_from_openclaw_updates_latest_reply(self) -> None:
        result = self.runtime.notify_from_openclaw(
            notification_type="manual.test",
            display_text="今天优先完成 Dashboard 联调。",
            spoken_text="我已经把重点放到屏幕上啦。",
            metadata={"mode": "focus"},
        )

        dashboard = self.read_dashboard()
        self.assertEqual(result["latest"]["display_text"], "今天优先完成 Dashboard 联调。")
        self.assertEqual(dashboard["mode"], "focus")
        self.assertEqual(dashboard["status_text"], "今天优先完成 Dashboard 联调。")
        self.assertEqual(
            dashboard["latest_reply"]["display_text"],
            "今天优先完成 Dashboard 联调。",
        )
        self.assertEqual(
            dashboard["latest_reply"]["spoken_text"],
            "我已经把重点放到屏幕上啦。",
        )

    def test_metadata_mode_writes_dashboard_mode(self) -> None:
        self.runtime._set_latest_reply(
            notification_type="generic.notify",
            display_text="进入专注",
            spoken_text="",
            reply_text="",
            tool_calls=[],
            metadata={"mode": "focus"},
            session_id="default",
            source="unit-test",
        )

        self.assertEqual(self.read_dashboard()["mode"], "focus")

    def test_care_tool_call_sets_dashboard_mode_care(self) -> None:
        self.runtime._set_latest_reply(
            notification_type="emotion.intervention",
            display_text="小安陪你缓一缓。",
            spoken_text="",
            reply_text="",
            tool_calls=[
                {
                    "name": "xiaoan.robot.care",
                    "arguments": {"text": "先喝口水吧。"},
                }
            ],
            metadata={},
            session_id="default",
            source="unit-test",
        )

        self.assertEqual(self.read_dashboard()["mode"], "care")

    def test_existing_dashboard_work_items_are_preserved(self) -> None:
        dashboard_path = self.runtime.openclaw_dashboard_path
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard_path.write_text(
            json.dumps(
                {
                    "schema": "xiaoan.dashboard.v1",
                    "updated_at": "old",
                    "mode": "idle",
                    "status_text": "old",
                    "next_item": {"title": "下一件事"},
                    "todos": [{"title": "任务"}],
                    "schedules": [{"title": "日程"}],
                    "reminders": [{"title": "提醒"}],
                    "latest_reply": {},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        self.runtime._set_latest_reply(
            notification_type="generic.notify",
            display_text="新回复",
            spoken_text="",
            reply_text="",
            tool_calls=[],
            metadata={},
            session_id="default",
            source="unit-test",
        )

        dashboard = self.read_dashboard()
        self.assertEqual(dashboard["next_item"], {"title": "下一件事"})
        self.assertEqual(dashboard["todos"], [{"title": "任务"}])
        self.assertEqual(dashboard["schedules"], [{"title": "日程"}])
        self.assertEqual(dashboard["reminders"], [{"title": "提醒"}])

    def test_openclaw_task_capture_is_mirrored_to_dashboard_todos(self) -> None:
        self.runtime._set_latest_reply(
            notification_type="asr.transcript.final",
            display_text="已加入待办：晚上1点做事事。",
            spoken_text="好呀，已经放进待办啦。",
            reply_text="好呀，已经帮你记下：晚上1点做事事。",
            tool_calls=[],
            metadata={"transcript": "小安把晚上1点做事事加入待办。"},
            session_id="voice-runtime",
            source="voice_runtime.text_loop",
            execution_result={
                "openclaw_result": {
                    "openclaw_raw": {
                        "capture": {
                            "status": "captured",
                            "kind": "task",
                            "title": "晚上1点做事事",
                            "content": "晚上1点做事事。",
                            "due_text": "晚上1点",
                        }
                    }
                }
            },
        )

        dashboard = self.read_dashboard()
        self.assertEqual(dashboard["todos"][0]["title"], "晚上1点做事事")
        self.assertEqual(dashboard["todos"][0]["due_text"], "晚上1点")
        self.assertEqual(dashboard["todos"][0]["source"], "openclaw_capture")
        self.assertEqual(
            dashboard["todos"][0]["transcript"],
            "小安把晚上1点做事事加入待办。",
        )
        self.assertEqual(dashboard["next_item"], dashboard["todos"][0])

    def test_openclaw_capture_needing_clarification_is_not_mirrored(self) -> None:
        self.runtime._set_latest_reply(
            notification_type="asr.transcript.final",
            display_text="这个提醒还缺时间。",
            spoken_text="还差一个时间，我再帮你定。",
            reply_text="这个提醒还缺时间。",
            tool_calls=[],
            metadata={"transcript": "提醒我喝水"},
            session_id="voice-runtime",
            source="voice_runtime.text_loop",
            execution_result={
                "openclaw_raw": {
                    "capture": {
                        "status": "needs_clarification",
                        "kind": "reminder",
                        "title": "喝水",
                    }
                }
            },
        )

        dashboard = self.read_dashboard()
        self.assertEqual(dashboard["reminders"], [])
        self.assertIsNone(dashboard["next_item"])

    def test_invalid_dashboard_json_recovers_to_minimal_valid_structure(self) -> None:
        dashboard_path = self.runtime.openclaw_dashboard_path
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard_path.write_text("{invalid", encoding="utf-8")

        self.runtime._set_latest_reply(
            notification_type="generic.notify",
            display_text="恢复显示",
            spoken_text="",
            reply_text="",
            tool_calls=[],
            metadata={},
            session_id="default",
            source="unit-test",
        )

        dashboard = self.read_dashboard()
        self.assertEqual(dashboard["schema"], "xiaoan.dashboard.v1")
        self.assertEqual(dashboard["todos"], [])
        self.assertEqual(dashboard["status_text"], "恢复显示")

    def test_sync_failure_does_not_break_notify_from_openclaw(self) -> None:
        self.runtime.openclaw_dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime.openclaw_dashboard_path.mkdir()

        result = self.runtime.notify_from_openclaw(
            notification_type="manual.test",
            display_text="同步失败也要返回",
        )

        self.assertEqual(result["latest"]["display_text"], "同步失败也要返回")
        self.assertEqual(result["notification"]["display_text"], "同步失败也要返回")

    def test_parse_args_accepts_openclaw_workspace(self) -> None:
        args = parse_args(["--openclaw-workspace", "/tmp/runtime-workspace"])

        self.assertEqual(args.openclaw_workspace, "/tmp/runtime-workspace")


if __name__ == "__main__":
    unittest.main()
