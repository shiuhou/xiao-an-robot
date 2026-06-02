"""Unit tests for EmotionMonitorSkill rule handling."""

from __future__ import annotations

import unittest

from agent.skills.emotion_monitor import EmotionMonitorSkill


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    async def send_expression(self, expression: str, duration_ms: int = 3000, loop: bool = False) -> dict:
        self.calls.append(("expression", expression, duration_ms, loop))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "display.expression"}}

    async def send_motion(self, action: str, params: dict | None = None, timeout_ms: int = 5000) -> dict:
        self.calls.append(("motion", action, params or {}, timeout_ms))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "motion.execute"}}

    async def send_tts(self, text: str) -> dict:
        self.calls.append(("tts", text))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "audio.play_tts"}}


class EmotionMonitorSkillTest(unittest.IsolatedAsyncioTestCase):
    async def test_high_fatigue_score_triggers_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 0.82,
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue")
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])

    async def test_neutral_low_fatigue_does_not_trigger_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 0.2,
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(gateway.calls, [])

    async def test_anxious_high_confidence_triggers_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "emotion_tag": "anxious",
            "confidence": 0.8,
            "fatigue_score": 0.2,
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "anxious")

    async def test_payload_wrapped_sad_trigger_is_parsed(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "type": "emotion.alert",
            "payload": {
                "emotion_tag": "sad",
                "confidence": 0.9,
                "fatigue_score": 0.1,
            },
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "sad")


if __name__ == "__main__":
    unittest.main()
