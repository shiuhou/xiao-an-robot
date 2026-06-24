import math
import unittest

import numpy as np

from base_station.perception.fatigue.face_metrics import (
    DEFAULT_EAR_CLOSED_THRESHOLD,
    DEFAULT_MAR_YAWN_THRESHOLD,
    EyeClosureTracker,
    FaceEventCounter,
    WFLW98_LEFT_EYE,
    WFLW98_RIGHT_EYE,
    classify_face_metrics,
    classify_fatigue_v0,
    compute_ear,
    compute_mar,
    should_run_periodic_task,
)


def make_landmarks():
    landmarks = np.zeros((98, 2), dtype=np.float32)

    right_eye_points = {
        60: (0.0, 0.0),
        61: (1.0, -1.0),
        62: (2.0, -1.2),
        63: (3.0, -1.0),
        64: (4.0, 0.0),
        65: (3.0, 1.0),
        66: (2.0, 1.2),
        67: (1.0, 1.0),
    }
    left_eye_points = {
        68: (10.0, 0.0),
        69: (11.0, -1.0),
        70: (12.0, -1.2),
        71: (13.0, -1.0),
        72: (14.0, 0.0),
        73: (13.0, 1.0),
        74: (12.0, 1.2),
        75: (11.0, 1.0),
    }
    inner_lip_points = {
        88: (20.0, 0.0),
        89: (21.0, -0.5),
        90: (22.0, -0.8),
        91: (23.0, -0.5),
        92: (24.0, 0.0),
        93: (23.0, 0.5),
        94: (22.0, 0.8),
        95: (21.0, 0.5),
    }

    for index, point in {**right_eye_points, **left_eye_points, **inner_lip_points}.items():
        landmarks[index] = point

    return landmarks


class FaceMetricsTests(unittest.TestCase):
    def test_default_state_thresholds_match_current_realtime_baseline(self):
        self.assertEqual(DEFAULT_EAR_CLOSED_THRESHOLD, 0.15)
        self.assertEqual(DEFAULT_MAR_YAWN_THRESHOLD, 0.9)

    def test_classify_face_metrics_uses_closed_eye_and_yawn_thresholds(self):
        self.assertEqual(
            classify_face_metrics(ear=0.14, mar=0.91),
            {"eye_closed": True, "yawning": True},
        )
        self.assertEqual(
            classify_face_metrics(ear=0.15, mar=0.9),
            {"eye_closed": False, "yawning": False},
        )
        self.assertEqual(
            classify_face_metrics(ear=None, mar=None),
            {"eye_closed": False, "yawning": False},
        )

    def test_classify_fatigue_v0_rejects_insufficient_observation_quality(self):
        result = classify_fatigue_v0(
            observation_quality=0.49,
            perclos=0.9,
            continuous_closure_s=2.0,
            yawn_count_window=3,
        )

        self.assertEqual(result["level"], "insufficient_evidence")
        self.assertIsNone(result["score"])
        self.assertEqual(result["evidence"], [])

    def test_classify_fatigue_v0_marks_long_closure_high(self):
        result = classify_fatigue_v0(
            observation_quality=0.8,
            perclos=0.05,
            continuous_closure_s=1.0,
            yawn_count_window=0,
        )

        self.assertEqual(result["level"], "HIGH")
        self.assertIn("LONG_CLOSURE", result["evidence"])
        self.assertTrue(67 <= result["score"] <= 100)

    def test_classify_fatigue_v0_marks_yawn_medium(self):
        result = classify_fatigue_v0(
            observation_quality=0.8,
            perclos=0.05,
            continuous_closure_s=0.0,
            yawn_count_window=1,
        )

        self.assertEqual(result["level"], "MEDIUM")
        self.assertEqual(result["evidence"], ["YAWN"])
        self.assertTrue(34 <= result["score"] <= 66)

    def test_classify_fatigue_v0_marks_normal_low(self):
        result = classify_fatigue_v0(
            observation_quality=0.8,
            perclos=0.02,
            continuous_closure_s=0.0,
            yawn_count_window=0,
        )

        self.assertEqual(result["level"], "LOW")
        self.assertEqual(result["evidence"], [])
        self.assertTrue(0 <= result["score"] <= 33)

    def test_classify_fatigue_v0_reports_rule_values_thresholds_and_fired_state(self):
        result = classify_fatigue_v0(
            observation_quality=0.8,
            perclos=0.21,
            continuous_closure_s=0.4,
            yawn_count_window=1,
        )

        rules = {rule["code"]: rule for rule in result["rules"]}
        self.assertEqual(set(rules), {"LONG_CLOSURE", "PERCLOS_HIGH", "PERCLOS_MID", "YAWN", "QUALITY"})
        self.assertEqual(
            rules["LONG_CLOSURE"],
            {
                "code": "LONG_CLOSURE",
                "label": "Long closure",
                "value": 0.4,
                "threshold": 1.0,
                "unit": "s",
                "tier": "strong",
                "fired": False,
            },
        )
        self.assertEqual(rules["PERCLOS_HIGH"]["value"], 0.21)
        self.assertEqual(rules["PERCLOS_HIGH"]["threshold"], 0.20)
        self.assertEqual(rules["PERCLOS_HIGH"]["unit"], "%")
        self.assertEqual(rules["PERCLOS_HIGH"]["tier"], "strong")
        self.assertTrue(rules["PERCLOS_HIGH"]["fired"])
        self.assertTrue(rules["PERCLOS_MID"]["fired"])
        self.assertEqual(rules["YAWN"]["value"], 1)
        self.assertEqual(rules["YAWN"]["threshold"], 1)
        self.assertEqual(rules["YAWN"]["tier"], "aux")
        self.assertTrue(rules["YAWN"]["fired"])
        self.assertEqual(rules["QUALITY"]["value"], 0.8)
        self.assertEqual(rules["QUALITY"]["threshold"], 0.5)
        self.assertEqual(rules["QUALITY"]["tier"], "gate")
        self.assertTrue(rules["QUALITY"]["fired"])

    def test_classify_fatigue_v0_reports_quality_rule_failed_when_insufficient(self):
        result = classify_fatigue_v0(
            observation_quality=0.49,
            perclos=0.3,
            continuous_closure_s=2.0,
            yawn_count_window=1,
        )

        rules = {rule["code"]: rule for rule in result["rules"]}
        self.assertEqual(result["level"], "insufficient_evidence")
        self.assertFalse(rules["QUALITY"]["fired"])
        self.assertEqual(rules["QUALITY"]["value"], 0.49)
        self.assertEqual(rules["QUALITY"]["threshold"], 0.5)

    def test_wflw98_eye_index_groups_match_star_definition(self):
        self.assertEqual(WFLW98_RIGHT_EYE, tuple(range(60, 68)))
        self.assertEqual(WFLW98_LEFT_EYE, tuple(range(68, 76)))

    def test_compute_ear_decreases_when_eye_vertical_distance_shrinks(self):
        open_landmarks = make_landmarks()
        closed_landmarks = make_landmarks()

        for index in (*WFLW98_RIGHT_EYE, *WFLW98_LEFT_EYE):
            if index not in (60, 64, 68, 72):
                center_y = 0.0
                closed_landmarks[index, 1] = center_y + (closed_landmarks[index, 1] - center_y) * 0.1

        self.assertGreater(compute_ear(open_landmarks), 0.4)
        self.assertLess(compute_ear(closed_landmarks), compute_ear(open_landmarks) * 0.2)

    def test_compute_mar_increases_when_inner_lip_opens(self):
        closed_landmarks = make_landmarks()
        open_landmarks = make_landmarks()

        for index in (89, 90, 91):
            open_landmarks[index, 1] -= 1.5
        for index in (93, 94, 95):
            open_landmarks[index, 1] += 1.5

        self.assertGreater(compute_mar(open_landmarks), compute_mar(closed_landmarks))
        self.assertGreater(compute_mar(open_landmarks), 0.9)

    def test_eye_closure_tracker_reports_perclos_over_valid_samples_only(self):
        tracker = EyeClosureTracker(ear_threshold=0.2, window_seconds=10.0)

        tracker.update(timestamp=0.0, ear=0.1, face_found=True)
        tracker.update(timestamp=2.0, ear=0.3, face_found=True)
        tracker.update(timestamp=4.0, ear=None, face_found=False)
        tracker.update(timestamp=6.0, ear=0.1, face_found=True)

        self.assertTrue(math.isclose(tracker.perclos, 0.5))

        tracker.update(timestamp=20.0, ear=0.3, face_found=True)

        self.assertEqual(tracker.perclos, 0.0)

    def test_face_event_counter_counts_short_eye_closure_as_blink_when_eye_reopens(self):
        counter = FaceEventCounter()

        counter.update({"eye_closed": False, "yawning": False}, timestamp=0.0)
        self.assertEqual(counter.blink_count, 0)
        self.assertEqual(counter.yawn_count, 0)

        counter.update({"eye_closed": True, "yawning": False}, timestamp=1.0)
        counter.update({"eye_closed": True, "yawning": False}, timestamp=1.2)
        self.assertEqual(counter.blink_count, 0)

        counter.update({"eye_closed": False, "yawning": False}, timestamp=1.4)
        self.assertEqual(counter.blink_count, 1)

        counter.update({"eye_closed": True, "yawning": False}, timestamp=3.0)
        counter.update({"eye_closed": False, "yawning": False}, timestamp=3.4)
        self.assertEqual(counter.blink_count, 2)

    def test_face_event_counter_does_not_count_long_eye_closure_as_blink(self):
        counter = FaceEventCounter(max_blink_seconds=0.8)

        counter.update({"eye_closed": True, "yawning": False}, timestamp=0.0)
        counter.update({"eye_closed": False, "yawning": False}, timestamp=10.0)

        self.assertEqual(counter.blink_count, 0)

    def test_face_event_counter_counts_yawn_rising_edges(self):
        counter = FaceEventCounter()

        counter.update({"eye_closed": False, "yawning": True}, timestamp=0.0)
        counter.update({"eye_closed": False, "yawning": True}, timestamp=1.0)
        self.assertEqual(counter.yawn_count, 1)

        counter.update({"eye_closed": False, "yawning": False}, timestamp=2.0)
        counter.update({"eye_closed": False, "yawning": True}, timestamp=3.0)
        self.assertEqual(counter.yawn_count, 2)

    def test_face_event_counter_resets_state_when_face_is_not_found(self):
        counter = FaceEventCounter()

        counter.update({"eye_closed": True, "yawning": True}, timestamp=0.0)
        counter.update(None)
        counter.update({"eye_closed": False, "yawning": False}, timestamp=1.0)
        counter.update({"eye_closed": True, "yawning": True}, timestamp=2.0)
        counter.update({"eye_closed": False, "yawning": True}, timestamp=2.3)

        self.assertEqual(counter.blink_count, 1)
        self.assertEqual(counter.yawn_count, 2)

    def test_should_run_periodic_task_runs_on_first_and_periodic_updates(self):
        self.assertTrue(should_run_periodic_task(update_count=1, every_n=5))
        self.assertFalse(should_run_periodic_task(update_count=2, every_n=5))
        self.assertFalse(should_run_periodic_task(update_count=4, every_n=5))
        self.assertTrue(should_run_periodic_task(update_count=5, every_n=5))
        self.assertTrue(should_run_periodic_task(update_count=10, every_n=5))

    def test_should_run_periodic_task_can_be_disabled(self):
        self.assertFalse(should_run_periodic_task(update_count=1, every_n=0))
        self.assertFalse(should_run_periodic_task(update_count=5, every_n=-1))
        self.assertFalse(should_run_periodic_task(update_count=1, every_n=5, enabled=False))


if __name__ == "__main__":
    unittest.main()
