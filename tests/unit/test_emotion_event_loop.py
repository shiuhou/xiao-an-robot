"""Unit tests for base_station.monitor.emotion_event_loop."""

from __future__ import annotations

import unittest

from base_station.monitor.emotion_event_loop import EmotionEventLoop


class FakeBrain:
    def __init__(self) -> None:
        self.events = []

    async def handle_event(self, event: dict) -> dict:
        self.events.append(event)
        return {
            "handled": True,
            "reason": "fake",
            "event": event,
        }


class EmotionEventLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_build_event_wraps_sample(self) -> None:
        loop = EmotionEventLoop(brain=FakeBrain())

        event = loop.build_event({
            "source": "face",
            "emotion_tag": "tired",
            "confidence": "0.9",
            "fatigue_score": "0.85",
        })

        self.assertEqual(event, {
            "type": "emotion.sample",
            "payload": {
                "source": "face",
                "emotion_tag": "tired",
                "confidence": 0.9,
                "fatigue_score": 0.85,
            },
        })

    async def test_build_event_uses_default_fields(self) -> None:
        loop = EmotionEventLoop(brain=FakeBrain())

        event = loop.build_event({})

        self.assertEqual(event["type"], "emotion.sample")
        self.assertEqual(event["payload"]["source"], "simulator")
        self.assertEqual(event["payload"]["emotion_tag"], "neutral")
        self.assertEqual(event["payload"]["confidence"], 0.0)
        self.assertEqual(event["payload"]["fatigue_score"], 0.0)

    async def test_build_event_preserves_vlm_metadata(self) -> None:
        loop = EmotionEventLoop(brain=FakeBrain())

        event = loop.build_event({
            "source": "face",
            "emotion_tag": "tired",
            "confidence": 0.9,
            "fatigue_score": 0.85,
            "frame_source": "fake_camera",
            "frame_id": "frame-1",
            "timestamp_ms": 123456,
            "session_id": "session-1",
            "project_id": 7,
            "vlm_triggered": True,
            "vlm_trigger_reason": "high_fatigue",
            "visual_reason": "eyes look tired",
            "vlm_observation": {"eyes": "tired"},
            "cv_sample": {"face_detected": True},
        })

        payload = event["payload"]
        self.assertEqual(event["type"], "emotion.sample")
        self.assertEqual(payload["frame_source"], "fake_camera")
        self.assertEqual(payload["frame_id"], "frame-1")
        self.assertEqual(payload["timestamp_ms"], 123456)
        self.assertEqual(payload["session_id"], "session-1")
        self.assertEqual(payload["project_id"], 7)
        self.assertEqual(payload["vlm_triggered"], True)
        self.assertEqual(payload["vlm_trigger_reason"], "high_fatigue")
        self.assertEqual(payload["visual_reason"], "eyes look tired")
        self.assertEqual(payload["vlm_observation"], {"eyes": "tired"})
        self.assertEqual(payload["cv_sample"], {"face_detected": True})

    async def test_build_event_preserves_false_vlm_triggered(self) -> None:
        loop = EmotionEventLoop(brain=FakeBrain())

        event = loop.build_event({
            "vlm_triggered": False,
            "vlm_trigger_reason": None,
            "visual_reason": "",
        })

        payload = event["payload"]
        self.assertIn("vlm_triggered", payload)
        self.assertFalse(payload["vlm_triggered"])
        self.assertIn("vlm_trigger_reason", payload)
        self.assertIsNone(payload["vlm_trigger_reason"])
        self.assertEqual(payload["visual_reason"], "")

    async def test_handle_sample_calls_brain_handle_event(self) -> None:
        brain = FakeBrain()
        loop = EmotionEventLoop(brain=brain)

        result = await loop.handle_sample({
            "source": "voice",
            "emotion_tag": "sad",
            "confidence": 0.8,
            "fatigue_score": 0.1,
        })

        self.assertTrue(result["handled"])
        self.assertEqual(len(brain.events), 1)
        self.assertEqual(brain.events[0]["type"], "emotion.sample")
        self.assertEqual(brain.events[0]["payload"]["emotion_tag"], "sad")

    async def test_build_event_passes_through_new_fields(self) -> None:
        loop = EmotionEventLoop(brain=FakeBrain())

        event = loop.build_event({
            "source": "openface_fatigue_metrics",
            "emotion_tag": "Sad",
            "confidence": 0.7,
            "fatigue_score": 0.72,
            "fatigue_level": "high",
            "observation_quality": 0.81,
            "evidence_codes": ["LONG_CLOSURE", "PERCLOS_HIGH"],
            "algorithm_version": "rule_v0",
            "presence_state": "present",
            "valence": "negative",
            "au_json": {"AU45": 0.9},
        })

        p = event["payload"]
        self.assertEqual(p["fatigue_level"], "high")
        self.assertEqual(p["observation_quality"], 0.81)
        self.assertEqual(p["evidence_codes"], ["LONG_CLOSURE", "PERCLOS_HIGH"])
        self.assertEqual(p["algorithm_version"], "rule_v0")
        self.assertEqual(p["presence_state"], "present")
        self.assertEqual(p["valence"], "negative")
        self.assertEqual(p["au_json"], {"AU45": 0.9})

    async def test_insufficient_evidence_preserves_none_fatigue_score(self) -> None:
        loop = EmotionEventLoop(brain=FakeBrain())

        event = loop.build_event({
            "source": "openface_fatigue_metrics",
            "emotion_tag": "Neutral",
            "confidence": 0.2,
            "fatigue_score": None,
            "fatigue_level": "insufficient_evidence",
        })

        self.assertIsNone(event["payload"]["fatigue_score"])
        self.assertEqual(event["payload"]["fatigue_level"], "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
