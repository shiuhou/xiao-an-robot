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


if __name__ == "__main__":
    unittest.main()
