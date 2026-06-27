"""Unit tests for EmotionMonitorSkill rule handling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.skills.emotion_monitor import EmotionMonitorSkill
from base_station.monitor.emotion_db import EmotionDB


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
        fatigue_score: float | None = 0.0,
        timestamp: int | None = None,
        *,
        polarity: str | None = None,
        valence: str | None = None,
        fatigue_level: str | None = None,
        observation_quality: float | None = None,
        evidence_codes=None,
        algorithm_version: str | None = None,
        presence_state: str | None = None,
        au_json=None,
    ) -> int:
        self.inserted.append({
            "source": source,
            "emotion_tag": emotion_tag,
            "confidence": confidence,
            "fatigue_score": fatigue_score,
            "timestamp": timestamp,
            "polarity": polarity,
            "valence": valence,
            "fatigue_level": fatigue_level,
            "observation_quality": observation_quality,
            "evidence_codes": evidence_codes,
            "algorithm_version": algorithm_version,
            "presence_state": presence_state,
            "au_json": au_json,
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
    avg_fatigue_score: float | None = 0.0,
    max_confidence: float = 0.0,
    top_emotion: str | None = None,
    emotions_count: dict | None = None,
    fatigue_level_top: str | None = None,
) -> dict:
    return {
        "count": count,
        "avg_fatigue_score": avg_fatigue_score,
        "max_confidence": max_confidence,
        "top_emotion": top_emotion,
        "emotions_count": emotions_count or {},
        "fatigue_level_top": fatigue_level_top,
    }


class EmotionMonitorSkillTest(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_fatigue_score_082_triggers_care(self) -> None:
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

    async def test_legacy_fatigue_score_02_does_not_trigger_care(self) -> None:
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

    async def test_openface_low_fatigue_score_33_does_not_trigger_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 33,
            "fatigue_level": "low",
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(gateway.calls, [])

    async def test_openface_high_fatigue_score_67_triggers_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 67,
            "fatigue_level": "low",
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue")
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])

    async def test_openface_high_level_triggers_without_numeric_score(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": None,
            "fatigue_level": "high",
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue")

    async def test_insufficient_evidence_none_score_does_not_trigger_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": None,
            "fatigue_level": "insufficient_evidence",
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

    async def test_openclaw_mode_returns_intervention_payload_without_local_care(self) -> None:
        gateway = FakeGateway()
        skill = EmotionMonitorSkill(gateway=gateway, execute_local_care=False)

        result = await skill.run({
            "source": "fake_qwen_vl",
            "frame_source": "fake_camera",
            "emotion_tag": "tired",
            "confidence": 0.9,
            "fatigue_score": 0.86,
            "timestamp_ms": 123456,
            "frame_id": 7,
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue")
        self.assertEqual(gateway.calls, [])
        payload = result["payload"]
        self.assertEqual(payload["emotion_tag"], "tired")
        self.assertEqual(payload["confidence"], 0.9)
        self.assertEqual(payload["fatigue_score"], 0.86)
        self.assertEqual(payload["reason"], "fatigue")
        self.assertEqual(payload["timestamp"], 123456)
        self.assertEqual(payload["timestamp_ms"], 123456)
        self.assertEqual(payload["source"], "fake_qwen_vl")
        self.assertEqual(payload["frame_source"], "fake_camera")
        self.assertEqual(payload["frame_id"], 7)

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

    async def test_memory_mode_forwards_openface_fields(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=33, emotions_count={"neutral": 1}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "source": "face",
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 33,
            "polarity": "负面",
            "valence": "negative",
            "fatigue_level": "low",
            "observation_quality": 0.91,
            "evidence_codes": ["PERCLOS_LOW"],
            "algorithm_version": "openface-v1",
            "presence_state": "present",
            "au_json": {"AU45": 0.4},
        })

        self.assertFalse(result["handled"])
        inserted = memory.inserted[0]
        self.assertEqual(inserted["polarity"], "负面")
        self.assertEqual(inserted["valence"], "negative")
        self.assertEqual(inserted["fatigue_level"], "low")
        self.assertEqual(inserted["observation_quality"], 0.91)
        self.assertEqual(inserted["evidence_codes"], ["PERCLOS_LOW"])
        self.assertEqual(inserted["algorithm_version"], "openface-v1")
        self.assertEqual(inserted["presence_state"], "present")
        self.assertEqual(inserted["au_json"], {"AU45": 0.4})

    async def test_memory_mode_preserves_none_fatigue_score(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(
            avg_fatigue_score=None,
            emotions_count={"neutral": 1},
            fatigue_level_top="insufficient_evidence",
        ))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "source": "face",
            "emotion_tag": "neutral",
            "confidence": 0.2,
            "fatigue_score": None,
            "fatigue_level": "insufficient_evidence",
        })

        self.assertFalse(result["handled"])
        self.assertIsNone(memory.inserted[0]["fatigue_score"])
        self.assertEqual(memory.inserted[0]["fatigue_level"], "insufficient_evidence")

    async def test_real_emotion_db_persists_openface_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "emotion_openface_fields.db")
            with EmotionDB(db_path) as memory:
                skill = EmotionMonitorSkill(gateway=FakeGateway(), memory=memory)

                result = await skill.run({
                    "source": "face",
                    "emotion_tag": "neutral",
                    "confidence": 0.8,
                    "fatigue_score": 33,
                    "polarity": "负面",
                    "valence": "negative",
                    "fatigue_level": "low",
                    "observation_quality": 0.91,
                    "evidence_codes": ["PERCLOS_LOW"],
                    "algorithm_version": "openface-v1",
                    "presence_state": "present",
                    "au_json": {"AU45": 0.4},
                })

                rows = memory.query_recent()

                self.assertFalse(result["handled"])
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row["polarity"], "负面")
                self.assertEqual(row["valence"], "negative")
                self.assertEqual(row["fatigue_level"], "low")
                self.assertEqual(row["observation_quality"], 0.91)
                self.assertEqual(json.loads(row["evidence_codes"]), ["PERCLOS_LOW"])
                self.assertEqual(row["algorithm_version"], "openface-v1")
                self.assertEqual(row["presence_state"], "present")
                self.assertEqual(json.loads(row["au_json"]), {"AU45": 0.4})

    async def test_memory_mode_high_average_fatigue_triggers_care(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=0.8, emotions_count={"neutral": 2}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 0.3,
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue_window")
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])

    async def test_memory_summary_average_33_does_not_trigger_care(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=33, emotions_count={"neutral": 2}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 33,
            "fatigue_level": "low",
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "normal")
        self.assertEqual(gateway.calls, [])

    async def test_memory_summary_average_67_triggers_care(self) -> None:
        gateway = FakeGateway()
        memory = FakeMemory(make_summary(avg_fatigue_score=67, emotions_count={"neutral": 2}))
        skill = EmotionMonitorSkill(gateway=gateway, memory=memory)

        result = await skill.run({
            "emotion_tag": "neutral",
            "confidence": 0.8,
            "fatigue_score": 67,
            "fatigue_level": "high",
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
        memory = FakeMemory(make_summary(avg_fatigue_score=0.8, emotions_count={"neutral": 2}))
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
