"""Integration tests for EmotionEventLoop -> XiaoAnBrain -> EmotionDB policy."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision
from base_station.monitor.emotion_db import EmotionDB
from base_station.monitor.emotion_event_loop import EmotionEventLoop


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


class EmotionEventLoopIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = EmotionDB(str(Path(self.temp_dir.name) / "emotion_loop.db"))
        self.gateway = FakeGateway()
        self.brain = XiaoAnBrain(
            gateway=self.gateway,
            memory=self.db,
            openclaw_adapter=FakeOpenClawAdapter(decision=OpenClawDecision(handled=False)),
        )
        self.loop = EmotionEventLoop(brain=self.brain)

    async def asyncTearDown(self) -> None:
        self.brain.close()
        self.temp_dir.cleanup()

    async def test_neutral_sample_does_not_trigger_intervention(self) -> None:
        result = await self.loop.handle_sample({
            "source": "face",
            "emotion_tag": "neutral",
            "confidence": 0.5,
            "fatigue_score": 0.2,
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(self.db.get_recent_summary()["count"], 1)

    async def test_consecutive_tired_samples_trigger_one_intervention(self) -> None:
        results = []
        for _ in range(3):
            results.append(await self.loop.handle_sample({
                "source": "face",
                "emotion_tag": "tired",
                "confidence": 0.9,
                "fatigue_score": 0.85,
            }))

        self.assertTrue(results[0]["handled"])
        self.assertEqual(results[0]["reason"], "fatigue_window")
        self.assertFalse(results[1]["handled"])
        self.assertFalse(results[2]["handled"])
        self.assertEqual([call[0] for call in self.gateway.calls], ["expression", "motion", "tts"])

    async def test_cooldown_prevents_repeated_intervention(self) -> None:
        first = await self.loop.handle_sample({
            "source": "face",
            "emotion_tag": "tired",
            "confidence": 0.9,
            "fatigue_score": 0.85,
        })
        second = await self.loop.handle_sample({
            "source": "face",
            "emotion_tag": "tired",
            "confidence": 0.9,
            "fatigue_score": 0.85,
        })

        self.assertTrue(first["handled"])
        self.assertFalse(second["handled"])
        self.assertEqual(second["reason"], "cooldown")
        self.assertEqual([call[0] for call in self.gateway.calls], ["expression", "motion", "tts"])


if __name__ == "__main__":
    unittest.main()
