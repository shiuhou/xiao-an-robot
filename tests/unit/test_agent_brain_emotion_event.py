"""Unit tests for XiaoAnBrain emotion event routing."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from agent.core.memory import XiaoAnMemoryStore
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


class RaisingOpenClawAdapter:
    def __init__(self) -> None:
        self.events = []

    def handle_event(self, event) -> OpenClawDecision:
        self.events.append(event)
        raise RuntimeError("openclaw failed")


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


class XiaoAnBrainEmotionEventTest(unittest.IsolatedAsyncioTestCase):
    async def test_tired_emotion_sample_triggers_local_fast_path(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(decision=OpenClawDecision(handled=False))
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(tired_summary()),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "emotion.sample",
            "payload": {
                "emotion_tag": "tired",
                "confidence": 0.9,
                "fatigue_score": 0.85,
            },
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["route"], "link_2_emotion_fast_path")
        self.assertEqual(result["openclaw_event_type"], "emotion.intervention")
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])

    async def test_tired_emotion_sample_records_intervention_memory_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "brain_emotion_memory.db")
            with XiaoAnMemoryStore(db_path) as context_memory:
                gateway = FakeGateway()
                openclaw_adapter = FakeOpenClawAdapter(
                    decision=OpenClawDecision(handled=False),
                )
                brain = XiaoAnBrain(
                    gateway=gateway,
                    memory=FakeMemory(tired_summary()),
                    openclaw_adapter=openclaw_adapter,
                    context_memory=context_memory,
                )

                result = await brain.handle_event({
                    "type": "emotion.sample",
                    "payload": {
                        "source": "face",
                        "frame_source": "fake_camera",
                        "emotion_tag": "tired",
                        "confidence": 0.9,
                        "fatigue_score": 0.85,
                        "session_id": "emotion-memory",
                        "timestamp_ms": 222333,
                        "frame_id": "frame-42",
                        "vlm_triggered": True,
                        "vlm_trigger_reason": "high_fatigue",
                        "visual_reason": "eyes look tired",
                        "vlm_observation": {"eyes": "tired"},
                        "cv_sample": {"face_detected": True},
                    },
                })

                events = context_memory.query_recent_events(event_type="emotion.intervention")

                self.assertTrue(result["handled"])
                self.assertEqual(len(events), 1)
                event = events[0]
                self.assertEqual(event["source"], "brain")
                self.assertEqual(event["session_id"], "emotion-memory")
                self.assertEqual(event["timestamp_ms"], 222333)
                metadata = event["payload"]["metadata"]
                self.assertEqual(metadata["route"], "link_2_emotion_fast_path")
                self.assertEqual(metadata["emotion_tag"], "tired")
                self.assertEqual(metadata["confidence"], 0.9)
                self.assertEqual(metadata["fatigue_score"], 0.85)
                self.assertEqual(metadata["source"], "face")
                self.assertEqual(metadata["frame_source"], "fake_camera")
                self.assertEqual(metadata["frame_id"], "frame-42")
                self.assertEqual(metadata["timestamp_ms"], 222333)
                self.assertEqual(metadata["trigger_reason"], "fatigue_window")
                self.assertEqual(metadata["vlm_triggered"], True)
                self.assertEqual(metadata["vlm_trigger_reason"], "high_fatigue")
                self.assertEqual(metadata["visual_reason"], "eyes look tired")
                self.assertEqual(metadata["vlm_observation"], {"eyes": "tired"})
                self.assertEqual(metadata["cv_sample"], {"face_detected": True})
                self.assertEqual(metadata["openclaw_event_type"], "emotion.intervention")
                self.assertTrue(metadata["handled"])

    async def test_emotion_intervention_memory_keeps_false_vlm_triggered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "brain_emotion_false_vlm.db")
            with XiaoAnMemoryStore(db_path) as context_memory:
                brain = XiaoAnBrain(
                    gateway=FakeGateway(),
                    memory=FakeMemory(tired_summary()),
                    openclaw_adapter=FakeOpenClawAdapter(decision=OpenClawDecision(handled=False)),
                    context_memory=context_memory,
                )

                await brain.handle_event({
                    "type": "emotion.sample",
                    "payload": {
                        "source": "face",
                        "emotion_tag": "tired",
                        "confidence": 0.9,
                        "fatigue_score": 0.85,
                        "vlm_triggered": False,
                        "vlm_trigger_reason": None,
                        "visual_reason": "",
                    },
                })

                events = context_memory.query_recent_events(event_type="emotion.intervention")

                self.assertEqual(len(events), 1)
                metadata = events[0]["payload"]["metadata"]
                self.assertIn("vlm_triggered", metadata)
                self.assertFalse(metadata["vlm_triggered"])
                self.assertIn("vlm_trigger_reason", metadata)
                self.assertIsNone(metadata["vlm_trigger_reason"])
                self.assertEqual(metadata["visual_reason"], "")

    async def test_tired_emotion_sample_is_forwarded_to_openclaw(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter(decision=OpenClawDecision(handled=False))
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(tired_summary()),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "emotion.sample",
            "payload": {
                "emotion_tag": "tired",
                "confidence": 0.9,
                "fatigue_score": 0.85,
                "session_id": "emotion-session-1",
            },
        })

        self.assertTrue(result["handled"])
        self.assertEqual(len(openclaw_adapter.events), 1)
        openclaw_event = openclaw_adapter.events[0]
        self.assertEqual(openclaw_event.type, "emotion.intervention")
        self.assertEqual(openclaw_event.source, "emotion_monitor")
        self.assertEqual(openclaw_event.session_id, "emotion-session-1")
        self.assertEqual(openclaw_event.context["trigger"]["emotion_tag"], "tired")
        self.assertEqual(openclaw_event.context["emotion_result"]["reason"], "fatigue_window")
        self.assertEqual(openclaw_event.context["emotion_tag"], "tired")
        self.assertEqual(openclaw_event.context["fatigue_score"], 0.85)
        self.assertEqual(openclaw_event.context["confidence"], 0.9)

    async def test_openclaw_reply_text_is_executed_as_emotion_followup(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=True, reply_text="我会继续留意你的状态。"),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(tired_summary()),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "emotion.sample",
            "payload": {
                "emotion_tag": "tired",
                "confidence": 0.9,
                "fatigue_score": 0.85,
            },
        })

        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts", "tts"])
        self.assertEqual(gateway.calls[-1][1], "我会继续留意你的状态。")
        self.assertEqual(result["openclaw_result"]["executed_actions"][0]["source"], "reply_text")

    async def test_neutral_emotion_sample_does_not_enter_openclaw(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter()
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(neutral_summary()),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "emotion.sample",
            "payload": {
                "emotion_tag": "neutral",
                "confidence": 0.5,
                "fatigue_score": 0.0,
            },
        })

        self.assertFalse(result["handled"])
        self.assertEqual(openclaw_adapter.events, [])
        self.assertNotEqual(result.get("route"), "link_2_emotion_fast_path")

    async def test_neutral_emotion_sample_does_not_record_intervention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "brain_emotion_neutral.db")
            with XiaoAnMemoryStore(db_path) as context_memory:
                brain = XiaoAnBrain(
                    gateway=FakeGateway(),
                    memory=FakeMemory(neutral_summary()),
                    openclaw_adapter=FakeOpenClawAdapter(),
                    context_memory=context_memory,
                )

                result = await brain.handle_event({
                    "type": "emotion.sample",
                    "payload": {
                        "source": "face",
                        "emotion_tag": "neutral",
                        "confidence": 0.5,
                        "fatigue_score": 0.0,
                    },
                })

                events = context_memory.query_recent_events(event_type="emotion.intervention")

                self.assertFalse(result["handled"])
                self.assertEqual(events, [])

    async def test_cooldown_does_not_record_duplicate_intervention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "brain_emotion_cooldown.db")
            with XiaoAnMemoryStore(db_path) as context_memory:
                brain = XiaoAnBrain(
                    gateway=FakeGateway(),
                    memory=FakeMemory(tired_summary()),
                    openclaw_adapter=FakeOpenClawAdapter(decision=OpenClawDecision(handled=False)),
                    context_memory=context_memory,
                )

                first = await brain.handle_event({
                    "type": "emotion.sample",
                    "payload": {
                        "source": "face",
                        "emotion_tag": "tired",
                        "confidence": 0.9,
                        "fatigue_score": 0.85,
                    },
                })
                second = await brain.handle_event({
                    "type": "emotion.sample",
                    "payload": {
                        "source": "face",
                        "emotion_tag": "tired",
                        "confidence": 0.9,
                        "fatigue_score": 0.85,
                    },
                })

                events = context_memory.query_recent_events(event_type="emotion.intervention")

                self.assertTrue(first["handled"])
                self.assertFalse(second["handled"])
                self.assertEqual(second["reason"], "cooldown")
                self.assertEqual(len(events), 1)

    async def test_emotion_fast_path_keeps_local_result_when_openclaw_raises(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = RaisingOpenClawAdapter()
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(tired_summary()),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "emotion.sample",
            "payload": {
                "emotion_tag": "tired",
                "confidence": 0.9,
                "fatigue_score": 0.85,
            },
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["route"], "link_2_emotion_fast_path")
        self.assertEqual(result["openclaw_event_type"], "emotion.intervention")
        self.assertIn("openclaw failed", result["openclaw_error"])
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])


if __name__ == "__main__":
    unittest.main()
