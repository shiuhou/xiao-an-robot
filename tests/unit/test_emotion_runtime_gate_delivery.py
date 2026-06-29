"""Gate delivery semantics for the runtime VLM path."""

from __future__ import annotations

import unittest

from base_station.monitor.emotion_event_loop import EmotionEventLoop
from base_station.monitor.emotion_runtime import VLMGatedCameraEmotionSource


class OneFrameSource:
    async def frames(self):
        yield {
            "source": "opencv_camera",
            "frame_id": 12,
            "timestamp_ms": 1234,
            "payload": "frame",
        }


class FixedCvPipeline:
    def __init__(self, sample: dict):
        self.sample = sample

    def process_frame(self, frame: dict) -> dict:
        return dict(self.sample)


class FixedGate:
    def __init__(self, should_trigger: bool, reason: str = "normal"):
        self.should_trigger = should_trigger
        self.reason = reason

    def evaluate(self, sample: dict, force_vlm: bool = False) -> dict:
        return {"should_trigger": self.should_trigger, "reason": self.reason}


class EmptyContextBuilder:
    def build(self, **kwargs) -> dict:
        return {}


class CountingVlm:
    def __init__(self, result: dict | None = None):
        self.result = result or {}
        self.calls = 0

    def predict(self, frame: dict, context: dict | None = None) -> dict:
        self.calls += 1
        return dict(self.result)


def make_cv_sample() -> dict:
    return {
        "source": "openface_fatigue_metrics",
        "emotion_tag": "neutral",
        "confidence": 0.62,
        "fatigue_score": 42.0,
        "polarity": "positive",
        "fatigue_level": "medium",
        "observation_quality": 0.91,
        "evidence_codes": ["PERCLOS_HIGH"],
        "algorithm_version": "rule_v0",
        "presence_state": "present",
        "valence": "neutral",
        "au_json": {"AU01": 0.2},
    }


class VLMGateDeliveryTest(unittest.IsolatedAsyncioTestCase):
    async def collect_samples(self, *, should_trigger: bool, vlm_result: dict | None = None):
        vlm = CountingVlm(vlm_result)
        source = VLMGatedCameraEmotionSource(
            frame_source=OneFrameSource(),
            cv_pipeline=FixedCvPipeline(make_cv_sample()),
            gate=FixedGate(should_trigger=should_trigger, reason="test_reason"),
            context_builder=EmptyContextBuilder(),
            vlm_model=vlm,
        )

        samples = [sample async for sample in source.samples()]
        return samples, vlm

    async def test_gate_false_does_not_yield_or_call_vlm(self):
        samples, vlm = await self.collect_samples(should_trigger=False)

        self.assertEqual(samples, [])
        self.assertEqual(vlm.calls, 0)

    async def test_gate_true_yields_sample_with_normalized_vlm_and_cv_sample(self):
        samples, vlm = await self.collect_samples(
            should_trigger=True,
            vlm_result={
                "expression_label": "tired",
                "confidence": 0.8,
                "evidence": "eyes_heavy",
                "face_observation": "eyes look heavy",
                "message": "take a rest",
                "fatigue_score": 0.9,
            },
        )

        self.assertEqual(vlm.calls, 1)
        self.assertEqual(len(samples), 1)
        sample = samples[0]
        self.assertTrue(sample["vlm_triggered"])
        self.assertEqual(sample["vlm_trigger_reason"], "test_reason")
        self.assertEqual(sample["cv_sample"]["fatigue_score"], 42.0)
        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["fatigue_score"], 42.0)
        self.assertEqual(sample["confidence"], 0.62)
        self.assertEqual(sample["fusion"]["decision"], "vlm_negative_aux_only")
        self.assertEqual(sample["fatigue_level"], "medium")
        self.assertEqual(sample["observation_quality"], 0.91)
        self.assertEqual(sample["au_json"], {"AU01": 0.2})
        self.assertEqual(sample["vlm"], {
            "executed": True,
            "status": "ok",
            "expression_label": "tired",
            "emotion_tag": "tired",
            "emotion_score": None,
            "confidence": 0.8,
            "fatigue_score": 0.9,
            "visual_reason": "",
            "vlm_observation": "",
            "evidence": ["eyes_heavy"],
            "face_observation": "eyes look heavy",
            "message": "take a rest",
            "valid_observation": None,
        })

    async def test_event_payload_contains_vlm_when_gate_true(self):
        samples, _vlm = await self.collect_samples(
            should_trigger=True,
            vlm_result={
                "expression_label": "tired",
                "confidence": 0.8,
                "fatigue_score": 0.8,
                "face_observation": "eyes look heavy",
            },
        )

        event_loop = EmotionEventLoop(brain=None)
        event = event_loop.build_event(samples[0])

        payload = event["payload"]
        self.assertEqual(event["type"], "emotion.sample")
        self.assertTrue(payload["vlm"]["executed"])
        self.assertEqual(payload["vlm"]["expression_label"], "tired")
        self.assertEqual(payload["emotion_tag"], "neutral")
        self.assertEqual(payload["fatigue_score"], 42.0)
        self.assertEqual(payload["fusion"]["decision"], "vlm_negative_aux_only")
        self.assertEqual(payload["fatigue_level"], "medium")
        self.assertEqual(payload["observation_quality"], 0.91)

    async def test_missing_vlm_fields_get_safe_defaults(self):
        samples, _vlm = await self.collect_samples(
            should_trigger=True,
            vlm_result={"expression_label": "neutral"},
        )

        self.assertEqual(samples[0]["vlm"], {
            "executed": True,
            "status": "ok",
            "expression_label": "neutral",
            "emotion_tag": "neutral",
            "emotion_score": None,
            "confidence": None,
            "fatigue_score": None,
            "visual_reason": "",
            "vlm_observation": "",
            "evidence": [],
            "face_observation": "",
            "message": "",
            "valid_observation": None,
        })


if __name__ == "__main__":
    unittest.main()
