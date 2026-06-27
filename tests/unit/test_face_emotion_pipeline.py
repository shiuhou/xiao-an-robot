"""Unit tests for FaceEmotionPipeline and CameraEmotionSource."""

from __future__ import annotations

import unittest

from base_station.perception.face_emotion_pipeline import CameraEmotionSource, FaceEmotionPipeline
from base_station.perception.fake_camera import FakeCameraFrameSource


def make_frame(frame_id: int = 1, timestamp_ms: int = 123456) -> dict:
    return {
        "source": "fake_camera",
        "frame_id": frame_id,
        "timestamp_ms": timestamp_ms,
        "width": 640,
        "height": 480,
        "payload": None,
    }


async def collect_samples(source: CameraEmotionSource) -> list[dict]:
    samples = []
    async for sample in source.samples():
        samples.append(sample)
    return samples


class CustomModel:
    def __init__(self) -> None:
        self.frames = []

    def predict(self, frame: dict) -> dict:
        self.frames.append(frame)
        return {
            "emotion_tag": "focused",
            "confidence": 0.77,
            "fatigue_score": 0.12,
            "source": "injected_model",
        }

class CustomModelWithoutSource:
    def predict(self, frame: dict) -> dict:
        return {
            "emotion_tag": "focused",
            "confidence": 0.77,
            "fatigue_score": 0.12,
        }


class FaceEmotionPipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_neutral_pattern_outputs_expected_sample(self) -> None:
        sample = FaceEmotionPipeline("neutral").process_frame(make_frame())

        self.assertEqual(sample["source"], "fake_face")
        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["confidence"], 0.5)
        self.assertEqual(sample["fatigue_score"], 0.2)

    async def test_tired_pattern_outputs_expected_sample(self) -> None:
        sample = FaceEmotionPipeline("tired").process_frame(make_frame())

        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertEqual(sample["confidence"], 0.9)
        self.assertEqual(sample["fatigue_score"], 0.85)

    async def test_anxious_pattern_outputs_expected_sample(self) -> None:
        sample = FaceEmotionPipeline("anxious").process_frame(make_frame())

        self.assertEqual(sample["emotion_tag"], "anxious")
        self.assertEqual(sample["confidence"], 0.88)
        self.assertEqual(sample["fatigue_score"], 0.4)

    async def test_mixed_pattern_cycles_expected_order(self) -> None:
        pipeline = FaceEmotionPipeline("mixed")
        samples = [pipeline.process_frame(make_frame(index + 1)) for index in range(6)]

        self.assertEqual(
            [sample["emotion_tag"] for sample in samples],
            ["neutral", "tired", "tired", "neutral", "anxious", "neutral"],
        )

    async def test_sample_keeps_frame_id_and_timestamp(self) -> None:
        sample = FaceEmotionPipeline("neutral").process_frame(make_frame(frame_id=7, timestamp_ms=999))

        self.assertEqual(sample["frame_id"], 7)
        self.assertEqual(sample["timestamp_ms"], 999)
        self.assertEqual(sample["frame_source"], "fake_camera")
        self.assertEqual(sample["width"], 640)
        self.assertEqual(sample["height"], 480)

    async def test_pipeline_uses_injected_model_prediction_and_keeps_source(self) -> None:
        model = CustomModel()
        frame = make_frame(frame_id=9, timestamp_ms=111)
        sample = FaceEmotionPipeline(model=model).process_frame(frame)

        self.assertEqual(sample["emotion_tag"], "focused")
        self.assertEqual(sample["confidence"], 0.77)
        self.assertEqual(sample["fatigue_score"], 0.12)
        self.assertEqual(sample["source"], "injected_model")
        self.assertEqual(sample["frame_source"], "fake_camera")
        self.assertEqual(sample["frame_id"], 9)
        self.assertEqual(sample["timestamp_ms"], 111)
        self.assertEqual(model.frames, [frame])

    async def test_pipeline_defaults_missing_model_source_to_fake_face(self) -> None:
        sample = FaceEmotionPipeline(model=CustomModelWithoutSource()).process_frame(make_frame())

        self.assertEqual(sample["source"], "fake_face")

    async def test_camera_emotion_source_converts_frames_to_samples(self) -> None:
        frame_source = FakeCameraFrameSource(count=2, interval_seconds=0)
        pipeline = FaceEmotionPipeline("tired")
        source = CameraEmotionSource(frame_source=frame_source, pipeline=pipeline)

        samples = await collect_samples(source)

        self.assertEqual(len(samples), 2)
        self.assertEqual([sample["emotion_tag"] for sample in samples], ["tired", "tired"])
        self.assertEqual([sample["frame_id"] for sample in samples], [1, 2])
        self.assertEqual([sample["frame_source"] for sample in samples], ["fake_camera", "fake_camera"])


if __name__ == "__main__":
    unittest.main()
