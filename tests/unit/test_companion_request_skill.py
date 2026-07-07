"""Unit tests for CompanionRequestSkill."""

from __future__ import annotations

import unittest

from agent.skills.companion_request import PRE_RESPONSE_TEXT, CompanionRequestSkill


class FakeRobotMotion:
    def __init__(self) -> None:
        self.calls = []

    async def show_expression(self, expression: str = "neutral") -> dict:
        self.calls.append(("show_expression", expression))
        return {"ok": True, "type": "display.expression"}

    async def move_out_of_dock(self) -> dict:
        self.calls.append(("move_out_of_dock",))
        return {"ok": True, "type": "motion.execute"}

    async def say(self, text: str) -> dict:
        self.calls.append(("say", text))
        return {"ok": True, "type": "audio.play_tts"}

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

    async def test_tired_text_calls_local_pre_response_with_tts(self) -> None:
        motion = FakeRobotMotion()
        skill = CompanionRequestSkill(robot_motion=motion)

        await skill.handle_text("我有点累")

        self.assertEqual([call[0] for call in motion.calls], ["show_expression", "say", "move_out_of_dock"])
        self.assertEqual(motion.calls[0][1], "caring")
        self.assertEqual(motion.calls[1][1], PRE_RESPONSE_TEXT)

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
