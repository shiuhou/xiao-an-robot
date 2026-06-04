"""Unit tests for mock face emotion model."""

from __future__ import annotations

import unittest

from base_station.perception.face_emotion_model import MockFaceEmotionModel


class MockFaceEmotionModelTest(unittest.TestCase):
    def test_neutral_outputs_expected_prediction(self) -> None:
        prediction = MockFaceEmotionModel("neutral").predict({"frame_id": 1})

        self.assertEqual(prediction["emotion_tag"], "neutral")
        self.assertEqual(prediction["confidence"], 0.5)
        self.assertEqual(prediction["fatigue_score"], 0.2)

    def test_tired_outputs_expected_prediction(self) -> None:
        prediction = MockFaceEmotionModel("tired").predict({"frame_id": 1})

        self.assertEqual(prediction["emotion_tag"], "tired")
        self.assertEqual(prediction["confidence"], 0.9)
        self.assertEqual(prediction["fatigue_score"], 0.85)

    def test_anxious_outputs_expected_prediction(self) -> None:
        prediction = MockFaceEmotionModel("anxious").predict({"frame_id": 1})

        self.assertEqual(prediction["emotion_tag"], "anxious")
        self.assertEqual(prediction["confidence"], 0.88)
        self.assertEqual(prediction["fatigue_score"], 0.4)

    def test_mixed_cycles_expected_predictions(self) -> None:
        model = MockFaceEmotionModel("mixed")
        predictions = [model.predict({"frame_id": index + 1}) for index in range(6)]

        self.assertEqual(
            [prediction["emotion_tag"] for prediction in predictions],
            ["neutral", "tired", "tired", "neutral", "anxious", "neutral"],
        )

    def test_predict_does_not_modify_frame(self) -> None:
        frame = {
            "source": "fake_camera",
            "frame_id": 1,
            "payload": object(),
        }
        original = frame.copy()

        MockFaceEmotionModel("tired").predict(frame)

        self.assertEqual(frame, original)


if __name__ == "__main__":
    unittest.main()
