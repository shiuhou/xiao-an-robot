"""Integration tests for OpenClaw runtime notification bridge API."""

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


class FakeRobotMotionSkill:
    def __init__(self) -> None:
        self.say_calls: list[str] = []
        self.expression_calls: list[str] = []

    def say(self, text: str) -> dict:
        self.say_calls.append(text)
        return {"ok": True, "command": "audio.play_tts", "text": text}

    def show_expression(self, expression: str) -> dict:
        self.expression_calls.append(expression)
        return {
            "ok": True,
            "command": "display.expression",
            "expression": expression,
        }


class ApiOpenClawNotifyIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "api-openclaw-notify.db"
        self.runtime = ApiRuntime(
            db_path=str(db_path),
            robot_ws_url="ws://127.0.0.1:65534/agent",
        )
        self.robot_motion = FakeRobotMotionSkill()
        self.runtime.robot_motion = self.robot_motion
        self.runtime.action_executor.robot_motion_skill = self.robot_motion
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

    def notify(self, body: dict) -> dict:
        status, response = self.post_json("/api/openclaw/notify", body)
        self.assertEqual(status, 200, response)
        self.assertTrue(response["ok"])
        return response["data"]

    def test_display_text_only_updates_latest_without_tts(self) -> None:
        result = self.notify({
            "type": "generic.notify",
            "display_text": "基站显示",
        })
        status, latest = self.get_json("/api/replies/latest")

        self.assertEqual(status, 200)
        self.assertEqual(self.robot_motion.say_calls, [])
        self.assertEqual(result["execution_result"]["executed_actions"], [])
        self.assertEqual(
            latest["data"]["latest"]["display_text"],
            "基站显示",
        )
        self.assertEqual(
            latest["data"]["latest"]["output_text"],
            "基站显示",
        )

    def test_spoken_text_triggers_one_tts(self) -> None:
        result = self.notify({
            "type": "reminder.due",
            "display_text": "喝水提醒",
            "spoken_text": "该喝水了",
        })
        status, latest = self.get_json("/api/replies/latest")

        self.assertEqual(status, 200)
        self.assertEqual(self.robot_motion.say_calls, ["该喝水了"])
        self.assertEqual(latest["data"]["latest"]["display_text"], "喝水提醒")
        self.assertEqual(latest["data"]["latest"]["spoken_text"], "该喝水了")
        self.assertEqual(
            result["execution_result"]["executed_actions"][0]["name"],
            "robot.say",
        )
        self.assertEqual(
            result["execution_result"]["executed_actions"][0]["source"],
            "spoken_text",
        )

    def test_suppress_auto_tts_keeps_latest_without_tts(self) -> None:
        result = self.notify({
            "type": "generic.notify",
            "display_text": "只显示",
            "spoken_text": "不要播报",
            "suppress_auto_tts": True,
        })
        status, latest = self.get_json("/api/replies/latest")

        self.assertEqual(status, 200)
        self.assertEqual(self.robot_motion.say_calls, [])
        self.assertEqual(result["execution_result"]["executed_actions"], [])
        self.assertTrue(latest["data"]["latest"]["suppress_auto_tts"])
        self.assertEqual(latest["data"]["latest"]["spoken_text"], "不要播报")

    def test_reply_text_legacy_still_triggers_tts(self) -> None:
        result = self.notify({
            "type": "generic.notify",
            "reply_text": "旧字段仍然播报",
        })

        self.assertEqual(self.robot_motion.say_calls, ["旧字段仍然播报"])
        self.assertEqual(
            result["execution_result"]["executed_actions"][0]["source"],
            "reply_text",
        )

    def test_expression_tool_call_reaches_robot_motion(self) -> None:
        result = self.notify({
            "type": "generic.notify",
            "tool_calls": [
                {
                    "name": "xiaoan.robot.expression",
                    "arguments": {"expression": "happy"},
                },
            ],
        })

        self.assertEqual(self.robot_motion.expression_calls, ["happy"])
        self.assertEqual(
            result["execution_result"]["executed_actions"][0]["name"],
            "xiaoan.robot.expression",
        )

    def test_spoken_text_and_robot_say_tool_call_do_not_double_speak(self) -> None:
        result = self.notify({
            "type": "generic.notify",
            "spoken_text": "不要播两次",
            "tool_calls": [
                {
                    "name": "xiaoan.robot.say",
                    "arguments": {"text": "工具播报一次"},
                },
            ],
        })

        self.assertEqual(self.robot_motion.say_calls, ["工具播报一次"])
        self.assertEqual(len(result["execution_result"]["executed_actions"]), 1)
        self.assertEqual(
            result["execution_result"]["executed_actions"][0]["name"],
            "xiaoan.robot.say",
        )


if __name__ == "__main__":
    unittest.main()
