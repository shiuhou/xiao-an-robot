"""Unit tests for CompanionRequestSkill."""

from __future__ import annotations

import unittest

from agent.skills.companion_request import LOCAL_CARE_MOTION, PRE_RESPONSE_TEXTS, CompanionRequestSkill


class FakeRobotMotion:
    def __init__(self) -> None:
        self.calls = []

    async def show_expression(self, expression: str = "neutral") -> dict:
        self.calls.append(("show_expression", expression))
        return {"ok": True, "type": "display.expression"}

    async def move_out_of_dock(self, **kwargs) -> dict:
        self.calls.append(("move_out_of_dock", kwargs))
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
        skill = CompanionRequestSkill(
            robot_motion=motion,
            pre_response_texts=("我在呢，先慢一点。",),
        )

        result = await skill.handle_text("我有点累")

        self.assertEqual([call[0] for call in motion.calls], ["show_expression", "say", "move_out_of_dock"])
        self.assertEqual(motion.calls[0][1], "caring")
        self.assertEqual(motion.calls[1][1], "我在呢，先慢一点。")
        self.assertEqual(motion.calls[2][1], LOCAL_CARE_MOTION)
        self.assertEqual(result["pre_response_text"], "我在呢，先慢一点。")
        self.assertEqual(result["local_care_motion"], LOCAL_CARE_MOTION)

    async def test_tired_text_picks_from_short_pre_response_pool(self) -> None:
        motion = FakeRobotMotion()
        skill = CompanionRequestSkill(robot_motion=motion)

        result = await skill.handle_text("陪陪我，我有点累")

        self.assertIn(result["pre_response_text"], PRE_RESPONSE_TEXTS)
        self.assertEqual(motion.calls[1][1], result["pre_response_text"])

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
