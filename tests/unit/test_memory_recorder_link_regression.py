"""Regression tests for link 2/3 memory event recording."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from agent.core.memory import XiaoAnMemoryStore
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision, OpenClawToolCall


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


class FakeEmotionMemory:
    def __init__(self, summary: dict) -> None:
        self.summary = summary
        self.inserted = []

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
        pass


def tired_summary() -> dict:
    return {
        "count": 1,
        "avg_fatigue_score": 0.85,
        "max_confidence": 0.9,
        "top_emotion": "tired",
        "emotions_count": {"tired": 1},
    }


def neutral_summary() -> dict:
    return {
        "count": 1,
        "avg_fatigue_score": 0.0,
        "max_confidence": 0.5,
        "top_emotion": "neutral",
        "emotions_count": {"neutral": 1},
    }


class MemoryRecorderLinkRegressionTest(unittest.IsolatedAsyncioTestCase):
    def make_db_path(self, temp_dir: str) -> str:
        return str(Path(temp_dir) / "link_memory_regression.db")

    def event_types(self, memory_store: XiaoAnMemoryStore) -> list[str]:
        return [
            event["event_type"]
            for event in memory_store.query_recent_events(limit=20)
        ]

    async def test_link_3_tired_asr_records_companion_request_and_care_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as context_memory:
                brain = XiaoAnBrain(
                    gateway=FakeGateway(),
                    memory=FakeEmotionMemory(neutral_summary()),
                    openclaw_adapter=FakeOpenClawAdapter(
                        decision=OpenClawDecision(handled=False),
                    ),
                    context_memory=context_memory,
                )

                result = await brain.handle_event({
                    "type": "asr.transcript",
                    "payload": {
                        "text": "我有点累",
                        "session_id": "link3-regression",
                    },
                })

                event_types = self.event_types(context_memory)

                self.assertEqual(result["route"], "link_3_companion_fast_path")
                self.assertIn("companion.request", event_types)
                self.assertIn("robot.care_action", event_types)
                self.assertNotEqual(context_memory.db_path, str(XiaoAnMemoryStore._default_db_path()))

    async def test_link_2_tired_emotion_records_intervention_and_care_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as context_memory:
                brain = XiaoAnBrain(
                    gateway=FakeGateway(),
                    memory=FakeEmotionMemory(tired_summary()),
                    openclaw_adapter=FakeOpenClawAdapter(
                        decision=OpenClawDecision(
                            handled=True,
                            tool_calls=[
                                OpenClawToolCall(
                                    name="xiaoan.robot.care",
                                    arguments={"text": "我在，先休息一下。"},
                                ),
                            ],
                        ),
                    ),
                    context_memory=context_memory,
                )

                result = await brain.handle_event({
                    "type": "emotion.sample",
                    "payload": {
                        "source": "face",
                        "emotion_tag": "tired",
                        "confidence": 0.9,
                        "fatigue_score": 0.85,
                        "session_id": "link2-regression",
                    },
                })

                event_types = self.event_types(context_memory)

                self.assertEqual(result["route"], "link_2_emotion_fast_path")
                self.assertIn("emotion.intervention", event_types)
                self.assertIn("robot.care_action", event_types)
                self.assertNotEqual(context_memory.db_path, str(XiaoAnMemoryStore._default_db_path()))

    async def test_link_2_neutral_emotion_records_no_intervention_or_care_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as context_memory:
                brain = XiaoAnBrain(
                    gateway=FakeGateway(),
                    memory=FakeEmotionMemory(neutral_summary()),
                    openclaw_adapter=FakeOpenClawAdapter(
                        decision=OpenClawDecision(handled=False),
                    ),
                    context_memory=context_memory,
                )

                result = await brain.handle_event({
                    "type": "emotion.sample",
                    "payload": {
                        "source": "face",
                        "emotion_tag": "neutral",
                        "confidence": 0.5,
                        "fatigue_score": 0.0,
                        "session_id": "neutral-regression",
                    },
                })

                event_types = self.event_types(context_memory)

                self.assertFalse(result["handled"])
                self.assertNotIn("emotion.intervention", event_types)
                self.assertNotIn("robot.care_action", event_types)
                self.assertNotEqual(context_memory.db_path, str(XiaoAnMemoryStore._default_db_path()))


if __name__ == "__main__":
    unittest.main()
