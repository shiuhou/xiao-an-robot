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


class FakeMemory:
    def __init__(self, summary: dict) -> None:
        self.summary = summary
        self.inserted = []
        self.summary_calls = []

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
        self.summary_calls.append({
            "seconds": seconds,
            "now_ms": now_ms,
        })
        return self.summary


def make_summary(
    count: int = 1,
    avg_fatigue_score: float = 0.0,
    max_confidence: float = 0.0,
    top_emotion: str | None = None,
    emotions_count: dict | None = None,
) -> dict:
    return {
        "count": count,
        "avg_fatigue_score": avg_fatigue_score,
        "max_confidence": max_confidence,
        "top_emotion": top_emotion,
        "emotions_count": emotions_count or {},
    }


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

    async def test_openface_fatigue_score_uses_0_to_100_scale(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.4,
            "fatigue_score": 80,
            "algorithm_version": "rule_v0",
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue")

    async def test_legacy_fractional_fatigue_score_is_scaled_to_100(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "source": "mock",
            "emotion_tag": "neutral",
            "confidence": 0.4,
            "fatigue_score": 0.8,
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue")

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

    async def test_low_openface_fatigue_score_does_not_trigger_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.4,
            "fatigue_score": 30,
            "algorithm_version": "rule_v0",
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(gateway.calls, [])

    async def test_missing_or_insufficient_fatigue_score_does_not_trigger_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.4,
            "fatigue_score": None,
            "fatigue_level": "insufficient_evidence",
            "observation_quality": 0.0,
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(gateway.calls, [])

    async def test_nested_vlm_fatigue_score_does_not_drive_primary_care_decision(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.4,
            "fatigue_score": 20,
            "algorithm_version": "rule_v0",
            "vlm": {
                "expression_label": "severe_sleepy",
                "confidence": 0.99,
                "fatigue_score": 0.95,
            },
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

    async def test_memory_mode_inserts_emotion_before_summary(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=0.2, emotions_count={"neutral": 1}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 0.3,
        })

        self.assertFalse(result["handled"])
        self.assertEqual(len(memory.inserted), 1)
        self.assertEqual(memory.inserted[0]["source"], "face")
        self.assertEqual(memory.inserted[0]["emotion_tag"], "neutral")
        self.assertEqual(memory.inserted[0]["confidence"], 0.8)
        self.assertEqual(memory.inserted[0]["fatigue_score"], 30.0)

    async def test_memory_mode_high_average_fatigue_triggers_care(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=80.0, emotions_count={"neutral": 2}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 0.3,
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue_window")
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])

    async def test_memory_mode_negative_emotion_count_triggers_care(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=0.2, emotions_count={"anxious": 2}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "emotion_tag": "anxious",
            "confidence": 0.8,
            "fatigue_score": 0.2,
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "negative_emotion_window")

    async def test_memory_mode_normal_window_does_not_trigger_care(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=0.2, emotions_count={"neutral": 3}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 0.2,
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(gateway.calls, [])

    async def test_memory_mode_cooldown_skips_second_intervention(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=80.0, emotions_count={"neutral": 2}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory, cooldown_seconds=300)

        first = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 0.8,
        })
        second = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 0.8,
        })

        self.assertTrue(first["handled"])
        self.assertFalse(second["handled"])
        self.assertEqual(second["reason"], "cooldown")


if __name__ == "__main__":
    unittest.main()
