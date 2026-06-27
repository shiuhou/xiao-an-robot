"""Unit tests for the manual OpenFace Route A trace probe helpers."""

from __future__ import annotations

import json
import numpy as np
import sys
import tempfile
import unittest
from unittest import mock

from tests.integration import probe_openface_routeA_trace as trace


class FakeCv2:
    CAP_PROP_POS_MSEC = 0
    CAP_PROP_FPS = 1
    CAP_PROP_POS_FRAMES = 2
    FONT_HERSHEY_SIMPLEX = 0
    LINE_AA = 0

    def __init__(self, frames, *, fps: float = 2.0, unreliable_pos_msec: bool = False) -> None:
        self._frames = list(frames)
        self._fps = fps
        self._unreliable_pos_msec = unreliable_pos_msec
        self.capture = None
        self.destroyed = False

    def VideoCapture(self, source):
        self.capture = FakeVideoCapture(
            source,
            self._frames,
            fps=self._fps,
            unreliable_pos_msec=self._unreliable_pos_msec,
        )
        return self.capture

    def imshow(self, *_args, **_kwargs) -> None:
        return None

    def waitKey(self, *_args, **_kwargs) -> int:
        return -1

    def destroyAllWindows(self) -> None:
        self.destroyed = True

    def putText(self, image, *_args, **_kwargs):
        return image

    def circle(self, image, *_args, **_kwargs):
        return image

    def rectangle(self, image, *_args, **_kwargs):
        return image

    def line(self, image, *_args, **_kwargs):
        return image


class FakeVideoCapture:
    def __init__(self, source, frames, *, fps: float, unreliable_pos_msec: bool) -> None:
        self.source = source
        self._frames = list(frames)
        self._fps = fps
        self._unreliable_pos_msec = unreliable_pos_msec
        self._index = 0
        self._pos_msec = 0.0
        self.set_calls = []
        self.released = False

    def isOpened(self) -> bool:
        return True

    def read(self):
        if self._index >= len(self._frames):
            return False, None
        image = self._frames[self._index]
        self._pos_msec = (self._index / self._fps) * 1000.0
        self._index += 1
        return True, image

    def get(self, prop):
        if prop == FakeCv2.CAP_PROP_POS_MSEC:
            return 0.0 if self._unreliable_pos_msec else self._pos_msec
        if prop == FakeCv2.CAP_PROP_FPS:
            return self._fps
        if prop == FakeCv2.CAP_PROP_POS_FRAMES:
            return self._index
        return 0.0

    def set(self, prop, value) -> bool:
        self.set_calls.append((prop, value))
        if prop == FakeCv2.CAP_PROP_POS_MSEC:
            self._index = min(int(round((value / 1000.0) * self._fps)), len(self._frames))
            self._pos_msec = float(value)
        return True

    def release(self) -> None:
        self.released = True


class FakePipeline:
    def __init__(self) -> None:
        self.calls = []

    def process_frame(self, frame, *, timestamp_ms=None):
        self.calls.append((frame, timestamp_ms))
        return {
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.5,
            "fatigue_score": 10.0,
            "frame_id": frame["frame_id"],
            "timestamp_ms": timestamp_ms,
        }


class FakeGate:
    fatigue_threshold = 70.0
    negative_confidence_threshold = 0.75
    negative_count_threshold = 2

    def evaluate(self, _cv_sample, *, force_vlm=False):
        return {"should_trigger": bool(force_vlm), "reason": "force" if force_vlm else "normal"}


def _run_trace_with_fakes(argv, fake_cv2: FakeCv2):
    args = trace.parse_args(argv)
    pipeline = FakePipeline()
    trace_state = {"last_obs": None}

    with mock.patch.dict(sys.modules, {"cv2": fake_cv2}):
        with mock.patch.object(trace, "build_traced_openface_pipeline", return_value=(pipeline, trace_state)):
            with mock.patch.object(trace, "build_vlm_components", return_value=(FakeGate(), None)):
                with mock.patch.object(trace, "draw_route_a_display", side_effect=lambda _cv2, frame, *_args, **_kwargs: frame["payload"]):
                    with mock.patch.object(trace.time, "sleep") as sleep_mock:
                        exit_code = trace.run_trace(args)

    return exit_code, pipeline, fake_cv2.capture, sleep_mock


class ProbeOpenFaceRouteATraceTest(unittest.TestCase):
    def test_parse_args_accepts_video_options(self) -> None:
        args = trace.parse_args([
            "--video",
            "manual_outputs/visual_eval/v0_1/videos/U01_N01_T00.mp4",
            "--video-step-seconds",
            "0.25",
        ])

        self.assertEqual(args.video, "manual_outputs/visual_eval/v0_1/videos/U01_N01_T00.mp4")
        self.assertEqual(args.video_step_seconds, 0.25)

    def test_parse_args_rejects_nonpositive_video_step(self) -> None:
        with self.assertRaises(SystemExit):
            trace.parse_args(["--video-step-seconds", "0"])

    def test_video_mode_passes_video_timestamp_to_process_frame(self) -> None:
        fake_cv2 = FakeCv2([
            np.zeros((2, 3, 3), dtype=np.uint8),
            np.ones((2, 3, 3), dtype=np.uint8),
        ])

        exit_code, pipeline, capture, _sleep_mock = _run_trace_with_fakes([
            "--video",
            "sample.mp4",
            "--video-step-seconds",
            "0.5",
            "--count",
            "1",
        ], fake_cv2)

        self.assertEqual(exit_code, 0)
        self.assertEqual(capture.source, "sample.mp4")
        self.assertEqual(len(pipeline.calls), 1)
        frame, timestamp_ms = pipeline.calls[0]
        self.assertEqual(frame["timestamp_ms"], 0)
        self.assertEqual(timestamp_ms, 0)

    def test_video_mode_exits_at_end_of_video(self) -> None:
        fake_cv2 = FakeCv2([
            np.zeros((2, 3, 3), dtype=np.uint8),
            np.ones((2, 3, 3), dtype=np.uint8),
        ])

        exit_code, pipeline, capture, _sleep_mock = _run_trace_with_fakes([
            "--video",
            "sample.mp4",
            "--video-step-seconds",
            "0.5",
            "--count",
            "0",
        ], fake_cv2)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(pipeline.calls), 2)
        self.assertTrue(capture.released)
        self.assertTrue(fake_cv2.destroyed)

    def test_video_mode_does_not_sleep(self) -> None:
        fake_cv2 = FakeCv2([np.zeros((2, 3, 3), dtype=np.uint8)])

        _exit_code, _pipeline, _capture, sleep_mock = _run_trace_with_fakes([
            "--video",
            "sample.mp4",
            "--count",
            "0",
        ], fake_cv2)

        sleep_mock.assert_not_called()

    def test_video_count_zero_processes_until_end(self) -> None:
        fake_cv2 = FakeCv2([
            np.zeros((2, 3, 3), dtype=np.uint8),
            np.ones((2, 3, 3), dtype=np.uint8),
            np.full((2, 3, 3), 2, dtype=np.uint8),
        ])

        _exit_code, pipeline, _capture, _sleep_mock = _run_trace_with_fakes([
            "--video",
            "sample.mp4",
            "--video-step-seconds",
            "0.5",
            "--count",
            "0",
        ], fake_cv2)

        self.assertEqual([call[0]["frame_id"] for call in pipeline.calls], [1, 2, 3])
        self.assertEqual([call[1] for call in pipeline.calls], [0, 500, 1000])

    def test_video_sampling_skips_unsampled_raw_frames_and_writes_only_samples(self) -> None:
        fake_cv2 = FakeCv2(
            [np.full((2, 3, 3), index, dtype=np.uint8) for index in range(5)],
            fps=10.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = f"{temp_dir}/trace.jsonl"
            _exit_code, pipeline, capture, _sleep_mock = _run_trace_with_fakes([
                "--video",
                "sample.mp4",
                "--video-step-seconds",
                "0.25",
                "--count",
                "0",
                "--jsonl",
                jsonl_path,
            ], fake_cv2)

            lines = [json.loads(line) for line in open(jsonl_path, encoding="utf-8")]

        self.assertEqual([call[0]["frame_id"] for call in pipeline.calls], [1, 4])
        self.assertEqual([call[1] for call in pipeline.calls], [0, 300])
        self.assertEqual([row["frame"]["frame_id"] for row in lines], [1, 4])
        self.assertEqual([row["cv_sample"]["frame_id"] for row in lines], [1, 4])
        self.assertEqual(len(lines), len(pipeline.calls))
        self.assertEqual(capture._index, 5)
        self.assertEqual(capture.set_calls, [])

    def test_video_count_limits_output_samples_not_raw_reads(self) -> None:
        fake_cv2 = FakeCv2(
            [np.full((2, 3, 3), index, dtype=np.uint8) for index in range(10)],
            fps=10.0,
        )

        _exit_code, pipeline, capture, _sleep_mock = _run_trace_with_fakes([
            "--video",
            "sample.mp4",
            "--video-step-seconds",
            "0.25",
            "--count",
            "2",
        ], fake_cv2)

        self.assertEqual([call[0]["frame_id"] for call in pipeline.calls], [1, 4])
        self.assertEqual([call[1] for call in pipeline.calls], [0, 300])
        self.assertEqual(capture._index, 4)

    def test_video_timestamp_falls_back_to_frame_number_and_fps(self) -> None:
        fake_cv2 = FakeCv2([
            np.zeros((2, 3, 3), dtype=np.uint8),
            np.ones((2, 3, 3), dtype=np.uint8),
        ], fps=4.0, unreliable_pos_msec=True)

        _exit_code, pipeline, _capture, _sleep_mock = _run_trace_with_fakes([
            "--video",
            "sample.mp4",
            "--video-step-seconds",
            "0.25",
            "--count",
            "0",
        ], fake_cv2)

        self.assertEqual([call[1] for call in pipeline.calls], [0, 250])

    def test_camera_mode_still_uses_camera_index_and_sleep(self) -> None:
        fake_cv2 = FakeCv2([np.zeros((2, 3, 3), dtype=np.uint8)])

        exit_code, pipeline, capture, sleep_mock = _run_trace_with_fakes([
            "--camera-index",
            "2",
            "--count",
            "1",
            "--interval",
            "0.25",
        ], fake_cv2)

        self.assertEqual(exit_code, 0)
        self.assertEqual(capture.source, 2)
        self.assertEqual(len(pipeline.calls), 1)
        self.assertIsNone(pipeline.calls[0][1])
        sleep_mock.assert_called_once_with(0.25)

    def test_sanitize_obs_summarizes_landmarks_without_dumping_array(self) -> None:
        class Landmarks:
            shape = (98, 2)

        obs = {
            "landmarks": Landmarks(),
            "face_confidence": 0.91,
            "emotion_label": "Neutral",
            "emotion_confidence": 0.82,
            "au": {"AU45": 0.5},
        }

        sanitized = trace.sanitize_obs(obs)

        self.assertEqual(sanitized["has_landmarks"], True)
        self.assertEqual(sanitized["landmarks_shape"], [98, 2])
        self.assertNotIn("landmarks", sanitized)
        self.assertEqual(sanitized["face_confidence"], 0.91)
        self.assertEqual(sanitized["au"], {"AU45": 0.5})

    def test_build_final_sample_for_triggered_vlm_matches_runtime_contract(self) -> None:
        """build_final_sample must mirror VLMGatedCameraEmotionSource.samples():

        top-level source stays on the CV sample; emotion_tag/confidence/
        fatigue_score follow the runtime conservative fusion policy.
        """
        cv_sample = {
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.4,
            "fatigue_score": 42.0,
            "fatigue_level": "medium",
            "observation_quality": 0.88,
            "presence_state": "present",
            "evidence_codes": ["PERCLOS_HIGH"],
        }
        vlm_result = {
            "source": "openvino_qwen_vl",
            "emotion_tag": "tired",
            "confidence": 0.9,
            "fatigue_score": 0.8,
            "visual_reason": "eyes look heavy",
            "vlm_observation": "needs rest",
        }
        gate_result = {"should_trigger": True, "reason": "force"}

        final_sample = trace.build_final_sample(cv_sample, gate_result, vlm_result)

        self.assertEqual(final_sample["source"], "openface_fatigue_metrics")
        self.assertEqual(final_sample["emotion_tag"], "tired")
        self.assertEqual(final_sample["confidence"], 0.9)
        self.assertEqual(final_sample["fatigue_score"], 0.8)
        self.assertEqual(final_sample["fusion"]["decision"], "vlm_promoted_negative")
        self.assertEqual(final_sample["fatigue_level"], "medium")
        self.assertEqual(final_sample["observation_quality"], 0.88)
        self.assertEqual(final_sample["presence_state"], "present")
        self.assertEqual(final_sample["evidence_codes"], ["PERCLOS_HIGH"])

        # VLM output is nested and the original CV sample is preserved.
        self.assertEqual(final_sample["vlm_triggered"], True)
        self.assertEqual(final_sample["vlm_trigger_reason"], "force")
        self.assertEqual(final_sample["cv_sample"], cv_sample)
        self.assertIn("vlm", final_sample)
        self.assertEqual(final_sample["vlm"]["executed"], True)
        self.assertEqual(final_sample["vlm"]["expression_label"], "tired")
        self.assertEqual(final_sample["vlm"]["confidence"], 0.9)
        self.assertNotIn("polarity", final_sample)

    def test_build_final_sample_low_confidence_vlm_does_not_override_top_level(self) -> None:
        cv_sample = {
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.4,
            "fatigue_score": 42.0,
        }
        vlm_result = {
            "emotion_tag": "anxious",
            "fatigue_score": 0.99,
        }
        gate_result = {"should_trigger": True, "reason": "high_fatigue"}

        final_sample = trace.build_final_sample(cv_sample, gate_result, vlm_result)

        self.assertEqual(final_sample["emotion_tag"], "neutral")
        self.assertEqual(final_sample["fatigue_score"], 42.0)
        self.assertEqual(final_sample["vlm"]["expression_label"], "anxious")

    def test_build_final_sample_skipped_gate_keeps_cv_sample_untouched(self) -> None:
        cv_sample = {
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.5,
            "fatigue_score": 10.0,
        }
        gate_result = {"should_trigger": False, "reason": "normal"}

        final_sample = trace.build_final_sample(cv_sample, gate_result, None)

        self.assertEqual(final_sample["vlm_triggered"], False)
        self.assertEqual(final_sample["vlm_trigger_reason"], "normal")
        self.assertNotIn("vlm", final_sample)
        self.assertNotIn("cv_sample", final_sample)
        self.assertEqual(final_sample["emotion_tag"], "neutral")
        self.assertEqual(final_sample["fatigue_score"], 10.0)

    def test_build_trace_row_omits_frame_payload_and_includes_event(self) -> None:
        frame = {
            "source": "opencv_camera",
            "frame_id": 7,
            "timestamp_ms": 123456,
            "width": 640,
            "height": 480,
            "payload": object(),
        }
        cv_sample = {
            "source": "openface_fatigue_metrics",
            "emotion_tag": "neutral",
            "confidence": 0.5,
            "fatigue_score": 10.0,
        }
        gate_result = {"should_trigger": False, "reason": "normal"}
        final_sample = trace.build_final_sample(cv_sample, gate_result, None)

        row = trace.build_trace_row(
            frame=frame,
            obs={"landmarks": None},
            cv_sample=cv_sample,
            gate_result=gate_result,
            vlm_result=None,
            final_sample=final_sample,
        )

        self.assertEqual(row["frame"], {
            "source": "opencv_camera",
            "frame_id": 7,
            "timestamp_ms": 123456,
            "width": 640,
            "height": 480,
        })
        self.assertNotIn("payload", row["frame"])
        self.assertEqual(row["vlm_result"], None)
        self.assertEqual(row["event"]["type"], "emotion.sample")
        self.assertEqual(row["event"]["payload"]["vlm_triggered"], False)
        self.assertNotIn("cv_sample", row["event"]["payload"])

    def test_build_gate_state_marks_triggered_rule(self) -> None:
        class Gate:
            fatigue_threshold = 70.0
            negative_confidence_threshold = 0.75
            negative_count_threshold = 2

        cv_sample = {
            "emotion_tag": "tired",
            "confidence": 0.82,
            "fatigue_score": 42.0,
        }
        gate_result = {"should_trigger": True, "reason": "negative_emotion"}

        gate_state = trace.build_gate_state(
            cv_sample=cv_sample,
            gate_result=gate_result,
            gate=Gate(),
            force_vlm=False,
            fatigue_score_window=[10.0, 42.0],
            negative_window=[0, 1],
        )

        rules = {rule["code"]: rule for rule in gate_state["rules"]}
        self.assertTrue(gate_state["should_trigger"])
        self.assertEqual(gate_state["reason"], "negative_emotion")
        self.assertTrue(rules["NEG_CONF"]["fired"])
        self.assertFalse(rules["HIGH_FATIGUE"]["fired"])
        self.assertEqual(gate_state["negative_count"], 1)

    def test_count_zero_keeps_route_a_probe_running(self) -> None:
        self.assertTrue(trace.should_process_frame(frame_id=1, count=0))
        self.assertTrue(trace.should_process_frame(frame_id=100, count=0))
        self.assertTrue(trace.should_process_frame(frame_id=3, count=3))
        self.assertFalse(trace.should_process_frame(frame_id=4, count=3))

    def test_cooldown_remaining_after_vlm_completion(self) -> None:
        self.assertEqual(trace.cooldown_remaining(now=100.0, last_completed=None, cooldown_seconds=30.0), 0.0)
        self.assertEqual(trace.cooldown_remaining(now=100.0, last_completed=80.0, cooldown_seconds=30.0), 10.0)
        self.assertEqual(trace.cooldown_remaining(now=100.0, last_completed=60.0, cooldown_seconds=30.0), 0.0)
        self.assertEqual(trace.cooldown_remaining(now=100.0, last_completed=80.0, cooldown_seconds=0.0), 0.0)

    def test_build_vlm_context_uses_current_cv_sample(self) -> None:
        context = trace.build_vlm_context({
            "emotion_tag": "tired",
            "confidence": 0.8,
            "fatigue_score": 72.0,
            "frame_id": 5,
        })

        self.assertEqual(context["cv"]["emotion_tag"], "tired")
        self.assertEqual(context["cv"]["confidence"], 0.8)
        self.assertEqual(context["cv"]["fatigue_score"], 72.0)
        self.assertEqual(context["cv"]["frame_id"], 5)
        self.assertEqual(context["history"]["count"], 0)

    def test_project_landmarks_uses_face_bbox_offset(self) -> None:
        obs = {
            "face_bbox": [100, 50, 180, 130],
            "landmarks": np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32),
        }

        points = trace.project_landmarks_to_frame(obs)

        self.assertEqual(points.tolist(), [[101.0, 52.0], [103.0, 54.0]])

    def test_build_obs_metrics_computes_ear_mar_and_au(self) -> None:
        landmarks = np.zeros((98, 2), dtype=np.float32)
        # Right eye indices 60..67: horizontal 10, average vertical 2 => EAR 0.2.
        landmarks[60] = [0, 0]
        landmarks[64] = [10, 0]
        landmarks[61] = [1, -1]
        landmarks[67] = [1, 1]
        landmarks[62] = [5, -1]
        landmarks[66] = [5, 1]
        landmarks[63] = [9, -1]
        landmarks[65] = [9, 1]
        # Left eye indices 68..75: same geometry.
        landmarks[68] = [20, 0]
        landmarks[72] = [30, 0]
        landmarks[69] = [21, -1]
        landmarks[75] = [21, 1]
        landmarks[70] = [25, -1]
        landmarks[74] = [25, 1]
        landmarks[71] = [29, -1]
        landmarks[73] = [29, 1]
        # Mouth: horizontal 20, average vertical 4 => MAR 0.2.
        landmarks[88] = [0, 20]
        landmarks[92] = [20, 20]
        landmarks[89] = [5, 18]
        landmarks[95] = [5, 22]
        landmarks[90] = [10, 18]
        landmarks[94] = [10, 22]
        landmarks[91] = [15, 18]
        landmarks[93] = [15, 22]

        metrics = trace.build_obs_metrics({
            "landmarks": landmarks,
            "face_confidence": 0.91,
            "emotion_label": "Neutral",
            "emotion_confidence": 0.8,
            "au": [
                0.11,
                0.22,
                0.33,
                0.44,
                0.55,
                0.66,
                0.77,
                0.88,
            ],
        })

        self.assertAlmostEqual(metrics["ear"], 0.2, places=3)
        self.assertAlmostEqual(metrics["mar"], 0.2, places=3)
        self.assertEqual(metrics["face_confidence"], 0.91)
        self.assertEqual(
            [label for label, _value in metrics["au_values"]],
            [
                "AU01 - Inner Brow Raiser",
                "AU02 - Outer Brow Raiser",
                "AU04 - Brow Lowerer",
                "AU06 - Cheek Raiser",
                "AU09 - Nose Wrinkler",
                "AU12 - Lip Corner Puller",
                "AU25 - Lips Part",
                "AU26 - Jaw Drop",
            ],
        )
        self.assertEqual(
            [value for _label, value in metrics["au_values"]],
            [
                0.11,
                0.22,
                0.33,
                0.44,
                0.55,
                0.66,
                0.77,
                0.88,
            ],
        )


if __name__ == "__main__":
    unittest.main()
