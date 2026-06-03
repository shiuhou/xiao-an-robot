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

    async def test_camera_emotion_source_converts_frames_to_samples(self) -> None:
        frame_source = FakeCameraFrameSource(count=2, interval_seconds=0)
        pipeline = FaceEmotionPipeline("tired")
        source = CameraEmotionSource(frame_source=frame_source, pipeline=pipeline)

        samples = await collect_samples(source)

        self.assertEqual(len(samples), 2)
        self.assertEqual([sample["emotion_tag"] for sample in samples], ["tired", "tired"])
        self.assertEqual([sample["frame_id"] for sample in samples], [1, 2])


if __name__ == "__main__":
    unittest.main()
