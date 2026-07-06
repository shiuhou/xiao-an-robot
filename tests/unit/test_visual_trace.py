"""Unit tests for Integration Console visual trace publication."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from base_station.integration_console.visual_trace import (
    VisualTracePublisher,
    project_landmarks_to_frame,
    render_annotated_frame,
)


class _Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _frame(frame_id: int = 7) -> dict:
    return {
        "source": "ws_video",
        "frame_id": frame_id,
        "timestamp_ms": 12345 + frame_id,
        "width": 120,
        "height": 100,
        "payload": np.zeros((100, 120, 3), dtype=np.uint8),
    }


def _observation() -> dict:
    points = np.zeros((98, 2), dtype=np.float32)
    points[:, 0] = np.linspace(2, 35, 98)
    points[:, 1] = np.linspace(3, 45, 98)
    return {
        "face_bbox": [10, 20, 70, 85],
        "landmarks": points,
        "face_confidence": 0.91,
        "emotion_label": "neutral",
        "emotion_confidence": 0.72,
        "au": {"AU01": 0.2},
    }


def _cv_sample(frame_id: int = 7) -> dict:
    return {
        "source": "openface_fatigue_metrics",
        "frame_id": frame_id,
        "timestamp_ms": 12345 + frame_id,
        "emotion_tag": "neutral",
        "confidence": 0.72,
        "fatigue_score": 20.0,
        "fatigue_level": "low",
        "observation_quality": 0.88,
        "evidence_codes": [],
        "presence_state": "present",
        "au_json": {"AU01": 0.2},
    }


def _gate_diagnostics(trigger: bool = False) -> dict:
    reason = "force" if trigger else "normal"
    return {
        "force": {"fired": trigger},
        "fatigue": {"value": 20.0, "threshold": 67.0, "fired": False},
        "single_negative": {
            "emotion": "neutral",
            "confidence": 0.72,
            "confidence_threshold": 0.75,
            "fired": False,
        },
        "negative_window": {
            "size": 10,
            "count": 0,
            "count_threshold": 4,
            "confidence_sum": 0.0,
            "confidence_sum_threshold": 2.0,
            "fired": False,
        },
        "result": {"should_trigger": trigger, "reason": reason},
    }


class VisualTraceGeometryTest(unittest.TestCase):
    def test_project_landmarks_adds_face_bbox_offset(self) -> None:
        observation = {
            "face_bbox": [10, 20, 50, 60],
            "landmarks": np.vstack([
                np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32),
                np.zeros((96, 2), dtype=np.float32),
            ]),
        }

        points = project_landmarks_to_frame(observation)

        np.testing.assert_allclose(points[:2], [[11.0, 22.0], [13.0, 24.0]])

    def test_render_does_not_mutate_source_frame(self) -> None:
        frame = _frame()
        before = frame["payload"].copy()

        rendered = render_annotated_frame(
            frame,
            _observation(),
            _cv_sample(),
            _gate_diagnostics(),
        )

        np.testing.assert_array_equal(frame["payload"], before)
        self.assertGreater(int(rendered.sum()), 0)


class VisualTracePublisherTest(unittest.TestCase):
    def test_publish_writes_only_owned_latest_files_with_matching_snapshot(self) -> None:
        wall = _Clock(200.0)
        monotonic = _Clock(100.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            publisher = VisualTracePublisher(
                temp_dir,
                max_fps=2.0,
                wall_clock=wall,
                monotonic_clock=monotonic,
            )

            token = publisher.observe_frame(
                frame=_frame(),
                observation=_observation(),
                cv_sample=_cv_sample(),
                gate_diagnostics=_gate_diagnostics(),
            )

            output = Path(temp_dir)
            state = json.loads((output / "latest_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["schema_version"], "visual_console_v1")
            self.assertEqual(state["snapshot_id"], token["snapshot_id"])
            self.assertEqual(state["frame_id"], 7)
            self.assertIn("ear", state["observation"])
            self.assertIn("mar", state["observation"])
            self.assertTrue((output / "latest_annotated.jpg").exists())
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                ["latest_annotated.jpg", "latest_state.json"],
            )

    def test_normal_frames_are_throttled_but_trigger_frame_is_not(self) -> None:
        clock = _Clock()
        with tempfile.TemporaryDirectory() as temp_dir:
            publisher = VisualTracePublisher(
                temp_dir,
                max_fps=2.0,
                wall_clock=clock,
                monotonic_clock=clock,
            )
            first = publisher.observe_frame(
                frame=_frame(1),
                observation=_observation(),
                cv_sample=_cv_sample(1),
                gate_diagnostics=_gate_diagnostics(),
            )
            clock.advance(0.1)
            skipped = publisher.observe_frame(
                frame=_frame(2),
                observation=_observation(),
                cv_sample=_cv_sample(2),
                gate_diagnostics=_gate_diagnostics(),
            )
            triggered = publisher.observe_frame(
                frame=_frame(3),
                observation=_observation(),
                cv_sample=_cv_sample(3),
                gate_diagnostics=_gate_diagnostics(trigger=True),
            )

            self.assertIsNotNone(first)
            self.assertIsNone(skipped)
            self.assertEqual(triggered["frame_id"], 3)
            self.assertNotIn("request_id", triggered)
            request_id = publisher.vlm_started(triggered, "force")
            self.assertTrue(request_id.startswith("vlm-"))
            self.assertEqual(
                sorted(path.name for path in Path(temp_dir).iterdir()),
                [
                    "latest_annotated.jpg",
                    "latest_state.json",
                    "vlm_state.json",
                    "vlm_trigger.jpg",
                ],
            )

    def test_old_vlm_completion_does_not_overwrite_active_request(self) -> None:
        clock = _Clock()
        with tempfile.TemporaryDirectory() as temp_dir:
            publisher = VisualTracePublisher(
                temp_dir,
                max_fps=2.0,
                wall_clock=clock,
                monotonic_clock=clock,
            )
            first = publisher.observe_frame(
                frame=_frame(1), observation=_observation(), cv_sample=_cv_sample(1),
                gate_diagnostics=_gate_diagnostics(trigger=True),
            )
            first_request = publisher.vlm_started(first, "force")
            clock.advance(0.1)
            second = publisher.observe_frame(
                frame=_frame(2), observation=_observation(), cv_sample=_cv_sample(2),
                gate_diagnostics=_gate_diagnostics(trigger=True),
            )
            second_request = publisher.vlm_started(second, "force")

            publisher.vlm_finished(
                first_request,
                status="done",
                vlm_result={"expression_label": "old"},
                final_sample={"fusion": {"decision": "old"}},
                latency_ms=500.0,
            )
            publisher.vlm_finished(
                second_request,
                status="done",
                vlm_result={"expression_label": "current"},
                final_sample={"fusion": {"decision": "cv_primary_vlm_aux"}},
                latency_ms=700.0,
            )

            state = json.loads(
                (Path(temp_dir) / "vlm_state.json").read_text(encoding="utf-8")
            )
            self.assertNotEqual(first_request, second_request)
            self.assertEqual(state["request_id"], second_request)
            self.assertEqual(state["result"]["expression_label"], "current")
            self.assertEqual(state["fusion"]["decision"], "cv_primary_vlm_aux")
            self.assertEqual(state["status"], "done")


if __name__ == "__main__":
    unittest.main()
