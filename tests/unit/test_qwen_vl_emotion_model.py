"""Unit tests for fake Qwen VL emotion model."""

from __future__ import annotations

import unittest

from base_station.perception.qwen_vl_emotion_model import FakeQwenVLEmotionModel, QwenVLEmotionModel


def make_frame(frame_id: int = 7, timestamp_ms: int = 123456) -> dict:
    return {
        "source": "opencv_camera",
        "frame_id": frame_id,
        "timestamp_ms": timestamp_ms,
        "width": 640,
        "height": 480,
        "payload": "image",
    }


class QwenVLEmotionModelTest(unittest.TestCase):
    def test_interface_predict_raises_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            QwenVLEmotionModel().predict(make_frame())

    def test_neutral_outputs_expected_format(self) -> None:
        sample = FakeQwenVLEmotionModel("neutral").predict(make_frame())

        self.assertEqual(set(sample), {
            "emotion_tag",
            "confidence",
            "fatigue_score",
            "visual_reason",
            "vlm_observation",
            "source",
            "frame_source",
            "frame_id",
            "timestamp_ms",
        })
        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["source"], "fake_qwen_vl")
        self.assertLess(sample["fatigue_score"], 0.3)
        self.assertLess(sample["confidence"], 0.7)

    def test_tired_outputs_high_fatigue_score(self) -> None:
        sample = FakeQwenVLEmotionModel("tired").predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertGreaterEqual(sample["fatigue_score"], 0.7)
        self.assertGreaterEqual(sample["confidence"], 0.8)

    def test_sad_outputs_sad_emotion_tag(self) -> None:
        sample = FakeQwenVLEmotionModel("sad").predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "sad")
        self.assertGreaterEqual(sample["confidence"], 0.8)

    def test_anxious_outputs_anxious_emotion_tag(self) -> None:
        sample = FakeQwenVLEmotionModel("anxious").predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "anxious")
        self.assertGreaterEqual(sample["confidence"], 0.8)

    def test_frame_metadata_is_preserved(self) -> None:
        sample = FakeQwenVLEmotionModel("neutral").predict(make_frame(frame_id=11, timestamp_ms=999))

        self.assertEqual(sample["frame_source"], "opencv_camera")
        self.assertEqual(sample["frame_id"], 11)
        self.assertEqual(sample["timestamp_ms"], 999)

    def test_missing_timestamp_generates_timestamp_ms(self) -> None:
        frame = make_frame()
        frame.pop("timestamp_ms")

        sample = FakeQwenVLEmotionModel("neutral").predict(frame)

        self.assertIsInstance(sample["timestamp_ms"], int)
        self.assertGreater(sample["timestamp_ms"], 0)

    def test_context_can_be_passed_without_breaking_predict(self) -> None:
        sample = FakeQwenVLEmotionModel("tired").predict(
            make_frame(),
            context={"recent_summary": {"avg_fatigue_score": 0.2}},
        )

        self.assertEqual(sample["emotion_tag"], "tired")

    def test_mixed_pattern_has_stable_sequence(self) -> None:
        model = FakeQwenVLEmotionModel("mixed")
        samples = [model.predict(make_frame(frame_id=index + 1)) for index in range(6)]

        self.assertEqual(
            [sample["emotion_tag"] for sample in samples],
            ["neutral", "tired", "sad", "anxious", "neutral", "neutral"],
        )

    def test_unknown_pattern_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported Qwen VL emotion pattern"):
            FakeQwenVLEmotionModel("excited")


if __name__ == "__main__":
    unittest.main()
