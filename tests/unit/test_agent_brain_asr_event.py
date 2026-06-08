"""Unit tests for XiaoAnBrain ASR transcript routing."""

from __future__ import annotations

import unittest

from agent.core.brain import XiaoAnBrain


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


class FakeMemory:
    def __init__(self) -> None:
        self.closed = False

    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        timestamp: int | None = None,
    ) -> int:
        return 1

    def get_recent_summary(self, seconds: int = 300, now_ms: int | None = None) -> dict:
        return {
            "count": 0,
            "avg_fatigue_score": 0.0,
            "max_confidence": 0.0,
            "top_emotion": None,
            "emotions_count": {},
        }

    def close(self) -> None:
        self.closed = True


class XiaoAnBrainASREventTest(unittest.IsolatedAsyncioTestCase):
    async def test_asr_transcript_tired_text_is_handled(self) -> None:
        gateway = FakeGateway()
        brain = XiaoAnBrain(gateway=gateway, memory=FakeMemory())

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "我有点累"},
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "asr_emotion_triggered")
        self.assertEqual(result["trigger_result"]["reason"], "fatigue_keyword")

    async def test_asr_transcript_triggers_robot_care_sequence(self) -> None:
        gateway = FakeGateway()
        brain = XiaoAnBrain(gateway=gateway, memory=FakeMemory())

        await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "我有点累"},
        })

        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])
        self.assertEqual(gateway.calls[0][1], "caring")
        self.assertEqual(gateway.calls[1][1], "move_out_of_dock")

    async def test_asr_transcript_normal_text_is_not_handled(self) -> None:
        gateway = FakeGateway()
        brain = XiaoAnBrain(gateway=gateway, memory=FakeMemory())

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "帮我查一下天气"},
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(gateway.calls, [])

    async def test_asr_transcript_missing_text_does_not_crash(self) -> None:
        gateway = FakeGateway()
        brain = XiaoAnBrain(gateway=gateway, memory=FakeMemory())

        result = await brain.handle_event({"type": "asr.transcript", "payload": {}})

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(gateway.calls, [])


if __name__ == "__main__":
    unittest.main()
