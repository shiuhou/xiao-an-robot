import math
import unittest

from base_station.perception.fatigue.affect_metrics import (
    AffectWindow,
    EXPRESSION_LABELS,
    LABEL_VALENCE,
    classify_valence,
)


class AffectMetricsTests(unittest.TestCase):
    def test_expression_labels_match_openface_source_of_truth(self):
        # demo2.py lives only in the OpenFace repo; assert the ported constant
        # against the known OpenFace expression_labels (kept in sync manually).
        self.assertEqual(
            EXPRESSION_LABELS,
            ["Neutral", "Happy", "Sad", "Surprise", "Fear", "Disgust", "Anger", "Contempt"],
        )

    def test_low_quality_forces_uncertain_affect_and_presence(self):
        window = AffectWindow(window_seconds=60.0)

        snapshot = window.update(
            timestamp=0.0,
            face_detected=True,
            observation_quality=0.49,
            emotion_label="Happy",
            emotion_confidence=0.95,
        )

        self.assertEqual(snapshot["presence_state"], "uncertain")
        self.assertEqual(snapshot["emotion_label"], "uncertain")
        self.assertIsNone(snapshot["emotion_confidence"])
        self.assertEqual(snapshot["valence"], "uncertain")

    def test_half_window_without_face_is_uncertain_not_absent_or_present(self):
        window = AffectWindow(window_seconds=60.0)

        for timestamp, face_detected in [
            (0.0, True),
            (5.0, True),
            (10.0, False),
            (15.0, False),
            (20.0, False),
        ]:
            snapshot = window.update(
                timestamp=timestamp,
                face_detected=face_detected,
                observation_quality=0.9,
                emotion_label="Neutral" if face_detected else None,
                emotion_confidence=0.8 if face_detected else None,
            )

        self.assertTrue(math.isclose(snapshot["face_presence_ratio"], 0.5))
        self.assertEqual(snapshot["presence_state"], "uncertain")

    def test_absent_boundary_when_face_presence_is_at_most_tenth(self):
        window = AffectWindow(window_seconds=60.0)

        for timestamp, face_detected in [
            (0.0, True),
            (1.0, False),
            (5.0, False),
            (10.0, False),
        ]:
            snapshot = window.update(
                timestamp=timestamp,
                face_detected=face_detected,
                observation_quality=0.9,
                emotion_label="Neutral" if face_detected else None,
                emotion_confidence=0.8 if face_detected else None,
            )

        self.assertTrue(math.isclose(snapshot["face_presence_ratio"], 0.1))
        self.assertEqual(snapshot["presence_state"], "absent")

    def test_happy_wins_window_majority_vote_over_neutral(self):
        window = AffectWindow(window_seconds=60.0)

        for timestamp, label, confidence in [
            (0.0, "Neutral", 0.6),
            (1.0, "Happy", 0.7),
            (2.0, "Happy", 0.9),
            (3.0, "Neutral", 0.8),
            (4.0, "Happy", 0.8),
        ]:
            snapshot = window.update(
                timestamp=timestamp,
                face_detected=True,
                observation_quality=0.9,
                emotion_label=label,
                emotion_confidence=confidence,
            )

        self.assertEqual(snapshot["emotion_label"], "Happy")
        self.assertTrue(math.isclose(snapshot["emotion_confidence"], 0.8))
        self.assertEqual(snapshot["valence"], "positive")

    def test_valence_mapping_covers_demo2_labels(self):
        self.assertEqual(classify_valence("Happy"), "positive")
        self.assertEqual(classify_valence("Sad"), "negative")
        self.assertEqual(classify_valence("Neutral"), "neutral")
        self.assertEqual(classify_valence("Surprise"), "neutral")
        self.assertEqual(classify_valence("Fear"), "negative")
        self.assertEqual(classify_valence("Disgust"), "negative")
        self.assertEqual(classify_valence("Anger"), "negative")
        self.assertEqual(classify_valence("Contempt"), "negative")
        self.assertEqual(set(LABEL_VALENCE), set(EXPRESSION_LABELS))

    def test_window_without_valid_emotion_frames_is_uncertain(self):
        window = AffectWindow(window_seconds=60.0)

        for timestamp in [0.0, 1.0, 2.0]:
            snapshot = window.update(
                timestamp=timestamp,
                face_detected=False,
                observation_quality=0.9,
                emotion_label=None,
                emotion_confidence=None,
            )

        self.assertEqual(snapshot["emotion_label"], "uncertain")
        self.assertIsNone(snapshot["emotion_confidence"])
        self.assertEqual(snapshot["valence"], "uncertain")

    def test_out_of_order_timestamps_do_not_create_negative_presence(self):
        window = AffectWindow(window_seconds=60.0)

        for timestamp in [10.0, 9.0, 12.0]:
            snapshot = window.update(
                timestamp=timestamp,
                face_detected=True,
                observation_quality=0.9,
                emotion_label="Happy",
                emotion_confidence=0.8,
            )

        self.assertGreaterEqual(snapshot["face_presence_ratio"], 0.0)
        self.assertLessEqual(snapshot["face_presence_ratio"], 1.0)
        self.assertIn(snapshot["presence_state"], {"present", "absent", "uncertain"})
        self.assertEqual(snapshot["timestamp_ms"], 12000)
        self.assertEqual(snapshot["window_sec"], 60.0)


if __name__ == "__main__":
    unittest.main()
