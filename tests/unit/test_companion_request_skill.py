"""Unit tests for CompanionRequestSkill."""

from __future__ import annotations

import unittest

from agent.skills.companion_request import CompanionRequestSkill


class FakeRobotMotion:
    def __init__(self) -> None:
        self.calls = []

    async def care_for_user(self, text: str = "") -> list[dict]:
        self.calls.append(("care_for_user", text))
        return [{"ok": True}]


class CompanionRequestSkillTest(unittest.IsolatedAsyncioTestCase):
    async def test_tired_text_triggers_handled_true(self) -> None:
        motion = FakeRobotMotion()
        skill = CompanionRequestSkill(robot_motion=motion)

        result = await skill.handle_text("我有点累")

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "asr_emotion_triggered")
        self.assertEqual(result["trigger_result"]["reason"], "fatigue_keyword")

    async def test_tired_text_calls_robot_care(self) -> None:
        motion = FakeRobotMotion()
        skill = CompanionRequestSkill(robot_motion=motion)

        await skill.handle_text("我有点累")

        self.assertEqual([call[0] for call in motion.calls], ["care_for_user"])

    async def test_normal_text_does_not_trigger(self) -> None:
        motion = FakeRobotMotion()
        skill = CompanionRequestSkill(robot_motion=motion)

        result = await skill.handle_text("帮我查一下天气")

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(motion.calls, [])

    async def test_empty_text_does_not_trigger(self) -> None:
        for text in ("", None, "   "):
            with self.subTest(text=text):
                motion = FakeRobotMotion()
                skill = CompanionRequestSkill(robot_motion=motion)

                result = await skill.handle_text(text)

                self.assertFalse(result["handled"])
                self.assertEqual(result["reason"], "normal")
                self.assertEqual(motion.calls, [])


if __name__ == "__main__":
    unittest.main()
