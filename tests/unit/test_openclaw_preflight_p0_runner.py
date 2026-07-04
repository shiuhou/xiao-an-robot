"""Unit tests for the OpenClaw P0 preflight runner plan."""

from __future__ import annotations

import unittest

from tools.ops.run_openclaw_preflight_p0 import PHRASES, build_p0_steps, format_console_json


class OpenClawPreflightP0RunnerTest(unittest.TestCase):
    def test_build_p0_steps_matches_acceptance_runbook(self) -> None:
        steps = build_p0_steps(device_id="xiaoan_robot_01")

        self.assertEqual([step.step_id for step in steps], [
            "P0-1",
            "P0-2",
            "P0-3",
            "P0-4",
            "P0-5",
            "P0-6",
            "P0-7",
            "P0-8",
        ])
        self.assertEqual(steps[1].payload["command"], "audio.play_tts")
        self.assertEqual(steps[1].payload["text"], PHRASES["hello_intro"])
        self.assertEqual(steps[4].payload["command"], "audio.play_local")
        self.assertEqual(steps[5].payload["expression"], "thinking")
        self.assertEqual(steps[6].payload["expression"], "speaking")
        self.assertEqual(steps[7].payload["action"], "stop")

    def test_chinese_phrases_are_real_unicode_text(self) -> None:
        self.assertEqual(PHRASES["hello_intro"], "你好，我是小安。")
        self.assertEqual(PHRASES["ack_help"], "好的，我来帮你。")
        self.assertEqual(PHRASES["repeat"], "请你再说一次。")

    def test_console_json_is_ascii_safe_for_windows_code_pages(self) -> None:
        text = format_console_json({"text": PHRASES["ack_help"]})

        self.assertIn("\\u6765", text)
        text.encode("cp950")


if __name__ == "__main__":
    unittest.main()
