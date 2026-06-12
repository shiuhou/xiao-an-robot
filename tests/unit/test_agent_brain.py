"""Unit tests for XiaoAnBrain event routing."""

from __future__ import annotations

import unittest

from agent.core.brain import XiaoAnBrain
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision


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
    def __init__(self, summary: dict) -> None:
        self.summary = summary
        self.inserted = []
        self.closed = False

    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        timestamp: int | None = None,
    ) -> int:
        self.inserted.append({
            "source": source,
            "emotion_tag": emotion_tag,
            "confidence": confidence,
            "fatigue_score": fatigue_score,
            "timestamp": timestamp,
        })
        return len(self.inserted)

    def get_recent_summary(self, seconds: int = 300, now_ms: int | None = None) -> dict:
        return self.summary

    def close(self) -> None:
        self.closed = True


class XiaoAnBrainTest(unittest.IsolatedAsyncioTestCase):
    async def test_emotion_sample_routes_to_emotion_monitor_skill(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory({
            "count": 1,
            "avg_fatigue_score": 0.85,
            "max_confidence": 0.9,
            "top_emotion": "tired",
            "emotions_count": {"tired": 1},
        })
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=memory,
            openclaw_adapter=FakeOpenClawAdapter(decision=OpenClawDecision(handled=False)),
        )

        result = await brain.handle_event({
            "type": "emotion.sample",
            "payload": {
                "source": "face",
                "emotion_tag": "tired",
                "confidence": 0.9,
                "fatigue_score": 0.85,
            },
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue_window")
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])
        self.assertEqual(len(memory.inserted), 1)

    async def test_unsupported_event_returns_unsupported_event_result(self) -> None:
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory({
                "count": 0,
                "avg_fatigue_score": 0.0,
                "max_confidence": 0.0,
                "top_emotion": None,
                "emotions_count": {},
            }),
        )

        result = await brain.handle_event({"type": "calendar.event", "payload": {}})

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "unsupported_event")

    async def test_close_closes_memory(self) -> None:
        memory = FakeMemory({
            "count": 0,
            "avg_fatigue_score": 0.0,
            "max_confidence": 0.0,
            "top_emotion": None,
            "emotions_count": {},
        })
        brain = XiaoAnBrain(gateway=FakeGateway(), memory=memory)

        brain.close()

        self.assertTrue(memory.closed)


if __name__ == "__main__":
    unittest.main()
