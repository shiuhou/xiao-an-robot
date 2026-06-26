"""Unit tests for the OpenClaw-facing Xiao An tool manifest."""

from __future__ import annotations

import unittest

from agent.core.xiaoan_tool_manifest import XIAOAN_TOOL_NAMES, tool_manifest


class XiaoAnToolManifestTest(unittest.TestCase):
    def test_manifest_contains_only_recommended_xiaoan_tools(self) -> None:
        expected = {
            "xiaoan.robot.say",
            "xiaoan.robot.expression",
            "xiaoan.robot.move_out",
            "xiaoan.robot.return_to_dock",
            "xiaoan.robot.care",
            "xiaoan.breathing.start",
            "xiaoan.emotion.snapshot",
            "xiaoan.runtime.status",
        }

        self.assertEqual(XIAOAN_TOOL_NAMES, expected)

    def test_each_tool_has_contract_fields(self) -> None:
        for tool in tool_manifest():
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["purpose"])
                self.assertIsInstance(tool["parameters"], dict)
                self.assertIsInstance(tool["returns"], dict)
                self.assertIsInstance(tool["failure"], dict)
                self.assertIn("ok", tool["returns"])
                self.assertIn("error", tool["failure"])

    def test_manifest_does_not_recommend_legacy_memory_tools(self) -> None:
        names = XIAOAN_TOOL_NAMES

        self.assertNotIn("note.add", names)
        self.assertNotIn("task.add", names)
        self.assertNotIn("reminder.add", names)
        self.assertNotIn("summary.daily", names)
        self.assertNotIn("work_context.record", names)


if __name__ == "__main__":
    unittest.main()
