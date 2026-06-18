import math
import unittest

from base_station.perception.fatigue.face_metrics import WindowAccumulator, evaluate_quality_gate


class WindowQualityTests(unittest.TestCase):
    def test_uniform_timestamps_match_legacy_counted_perclos(self):
        accumulator = WindowAccumulator(window_seconds=60.0)
        eye_states = [True, True, True, True, True]

        for timestamp, eye_closed in enumerate(eye_states):
            snapshot = accumulator.update(
                timestamp=float(timestamp),
                face_detected=True,
                landmarks_valid=True,
                face_confidence=0.9,
                eye_closed=eye_closed,
            )

        legacy_counted_perclos = sum(1 for eye_closed in eye_states if eye_closed) / len(eye_states)
        self.assertTrue(math.isclose(snapshot["perclos"], legacy_counted_perclos))

    def test_irregular_timestamps_weight_closed_duration_by_elapsed_time(self):
        accumulator = WindowAccumulator(window_seconds=60.0)

        for timestamp, eye_closed in [
            (0.0, False),
            (1.0, True),
            (11.0, True),
            (12.0, False),
            (20.0, False),
        ]:
            snapshot = accumulator.update(
                timestamp=timestamp,
                face_detected=True,
                landmarks_valid=True,
                face_confidence=0.9,
                eye_closed=eye_closed,
            )

        self.assertTrue(math.isclose(snapshot["perclos"], 11 / 20))

    def test_half_window_without_face_reports_half_face_presence(self):
        accumulator = WindowAccumulator(window_seconds=60.0)

        for timestamp, face_detected in [
            (0.0, True),
            (5.0, True),
            (10.0, False),
            (15.0, False),
            (20.0, False),
        ]:
            snapshot = accumulator.update(
                timestamp=timestamp,
                face_detected=face_detected,
                landmarks_valid=face_detected,
                face_confidence=1.0 if face_detected else 0.0,
                eye_closed=False,
            )

        self.assertTrue(math.isclose(snapshot["face_presence_ratio"], 0.5))

    def test_no_face_duration_does_not_increase_perclos(self):
        accumulator = WindowAccumulator(window_seconds=60.0)

        for timestamp, face_detected, landmarks_valid, eye_closed in [
            (0.0, True, True, False),
            (5.0, False, False, True),
            (10.0, False, False, True),
            (15.0, True, True, False),
        ]:
            snapshot = accumulator.update(
                timestamp=timestamp,
                face_detected=face_detected,
                landmarks_valid=landmarks_valid,
                face_confidence=0.8 if face_detected else 0.0,
                eye_closed=eye_closed,
            )

        self.assertEqual(snapshot["perclos"], 0.0)

    def test_observation_quality_uses_minimum_of_four_quality_terms(self):
        accumulator = WindowAccumulator(window_seconds=60.0)

        for timestamp, face_detected, landmarks_valid, confidence in [
            (0.0, True, True, 0.9),
            (2.0, True, True, 0.9),
            (4.0, True, False, 0.9),
            (6.0, True, False, 0.9),
            (8.0, False, False, 0.0),
            (10.0, False, False, 0.0),
        ]:
            snapshot = accumulator.update(
                timestamp=timestamp,
                face_detected=face_detected,
                landmarks_valid=landmarks_valid,
                face_confidence=confidence,
                eye_closed=False,
            )

        expected_terms = (
            snapshot["valid_frame_ratio"],
            snapshot["face_presence_ratio"],
            snapshot["landmark_valid_ratio"],
            snapshot["mean_face_confidence"],
        )
        self.assertTrue(math.isclose(snapshot["observation_quality"], min(expected_terms)))
        self.assertTrue(math.isclose(snapshot["observation_quality"], 0.4))

    def test_quality_gate_rejects_low_observation_quality(self):
        result = evaluate_quality_gate(observation_quality=0.49, q_min=0.5)

        self.assertEqual(
            result,
            {"fatigue_level": "insufficient_evidence", "fatigue_risk_score": None},
        )

    def test_quality_gate_passes_sufficient_observation_quality(self):
        self.assertEqual(evaluate_quality_gate(observation_quality=0.5, q_min=0.5), {"gate": "pass"})

    def test_single_sample_zero_span_returns_safe_defaults(self):
        accumulator = WindowAccumulator(window_seconds=60.0)

        snapshot = accumulator.update(
            timestamp=10.0,
            face_detected=True,
            landmarks_valid=True,
            face_confidence=0.8,
            eye_closed=True,
        )

        self.assertEqual(snapshot["window_span_seconds"], 0.0)
        self.assertEqual(snapshot["valid_duration"], 0.0)
        self.assertEqual(snapshot["perclos"], 0.0)
        self.assertEqual(snapshot["observation_quality"], 0.0)
        self.assertEqual(snapshot["quality_gate"], {"fatigue_level": "insufficient_evidence", "fatigue_risk_score": None})

    def test_out_of_order_timestamps_do_not_create_negative_durations(self):
        accumulator = WindowAccumulator(window_seconds=60.0)

        for timestamp in [10.0, 9.0, 12.0]:
            snapshot = accumulator.update(
                timestamp=timestamp,
                face_detected=True,
                landmarks_valid=True,
                face_confidence=1.0,
                eye_closed=True,
            )

        self.assertGreaterEqual(snapshot["window_span_seconds"], 0.0)
        self.assertGreaterEqual(snapshot["valid_duration"], 0.0)
        self.assertGreaterEqual(snapshot["closed_duration"], 0.0)
        self.assertTrue(0.0 <= snapshot["perclos"] <= 1.0)


if __name__ == "__main__":
    unittest.main()
