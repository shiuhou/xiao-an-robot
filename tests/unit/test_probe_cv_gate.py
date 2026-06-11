"""Unit tests for tools.probe_cv_gate."""

from __future__ import annotations

import io
import json
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import probe_cv_gate


STABLE_KEYS = {
    "frame_id",
    "timestamp_ms",
    "frame_source",
    "emotion_tag",
    "cv_emotion_raw",
    "confidence",
    "fatigue_score",
    "face_detected",
    "calibrated",
    "source",
    "gate_triggered",
    "gate_reason",
}


class FakeOpenCVCameraFrameSource:
    closed = False
    raise_on_open: Exception | None = None

    def __init__(
        self,
        camera_index: int = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self._frame_id = 0
        self._opened = False

    def open(self) -> None:
        if type(self).raise_on_open is not None:
            raise type(self).raise_on_open
        self._opened = True

    def read_frame(self) -> dict:
        if not self._opened:
            self.open()
        self._frame_id += 1
        return {
            "source": "opencv_camera",
            "frame_id": self._frame_id,
            "timestamp_ms": 1000 + self._frame_id,
            "width": self.width or 640,
            "height": self.height or 480,
            "payload": object(),
        }

    async def frames(self):
        try:
            while True:
                yield self.read_frame()
        finally:
            self.close()

    def close(self) -> None:
        type(self).closed = True


class FakeOpenVINOFaceEmotionModel:
    instances = []
    raise_on_init: Exception | None = None

    def __init__(self, model_path: str | None = None, device: str = "CPU") -> None:
        if type(self).raise_on_init is not None:
            raise type(self).raise_on_init
        self.model_path = model_path
        self.device = device
        type(self).instances.append(self)

    def predict(self, frame: dict) -> dict:
        return {
            "emotion_tag": "tired",
            "cv_emotion_raw": "sadness",
            "confidence": 0.91,
            "fatigue_score": 0.82,
            "face_detected": True,
            "calibrated": False,
            "source": "openvino_face",
            "frame_source": frame.get("source"),
            "frame_id": frame.get("frame_id"),
            "timestamp_ms": frame.get("timestamp_ms"),
        }


class ProbeCVGateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeOpenCVCameraFrameSource.closed = False
        FakeOpenCVCameraFrameSource.raise_on_open = None
        FakeOpenVINOFaceEmotionModel.instances = []
        FakeOpenVINOFaceEmotionModel.raise_on_init = None

    def make_args(
        self,
        *,
        pattern: str = "neutral",
        count: int = 2,
        enable_gate: bool = False,
        force_gate: bool = False,
        save_jsonl: str | None = None,
    ):
        return probe_cv_gate.parse_args([
            "--source",
            "fake_camera",
            "--model-backend",
            "mock",
            "--pattern",
            pattern,
            "--count",
            str(count),
            "--no-show",
            *(["--enable-gate"] if enable_gate else []),
            *(["--force-gate"] if force_gate else []),
            *(["--save-jsonl", save_jsonl] if save_jsonl else []),
        ])

    async def test_fake_camera_mock_neutral_runs_fixed_count_without_crashing(self) -> None:
        with redirect_stdout(io.StringIO()):
            rows = await probe_cv_gate.probe_cv_gate(self.make_args(pattern="neutral", count=3))

        self.assertEqual(len(rows), 3)
        self.assertEqual([row["frame_id"] for row in rows], [1, 2, 3])
        self.assertEqual({row["emotion_tag"] for row in rows}, {"neutral"})
        self.assertTrue(all(STABLE_KEYS.issubset(row) for row in rows))

    async def test_fake_camera_mock_tired_outputs_fatigue_and_gate_result(self) -> None:
        with redirect_stdout(io.StringIO()):
            rows = await probe_cv_gate.probe_cv_gate(
                self.make_args(pattern="tired", count=2, enable_gate=True)
            )

        self.assertEqual([row["fatigue_score"] for row in rows], [0.85, 0.85])
        self.assertTrue(all(row["gate_triggered"] for row in rows))
        self.assertEqual({row["gate_reason"] for row in rows}, {"high_fatigue"})

    async def test_save_jsonl_writes_requested_lines_with_stable_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = str(Path(temp_dir) / "cv_gate_debug.jsonl")
            with redirect_stdout(io.StringIO()):
                rows = await probe_cv_gate.probe_cv_gate(
                    self.make_args(pattern="neutral", count=2, enable_gate=True, save_jsonl=output_path)
                )

            lines = Path(output_path).read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(rows), 2)
        self.assertEqual(len(lines), 2)
        parsed = [json.loads(line) for line in lines]
        self.assertTrue(all(STABLE_KEYS.issubset(row) for row in parsed))

    def test_cli_no_show_count_two_returns_zero(self) -> None:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code = probe_cv_gate.main([
                "--source",
                "fake_camera",
                "--model-backend",
                "mock",
                "--pattern",
                "neutral",
                "--count",
                "2",
                "--no-show",
            ])

        self.assertEqual(exit_code, 0)

    def test_parser_accepts_opencv_camera_options(self) -> None:
        args = probe_cv_gate.parse_args([
            "--source",
            "opencv_camera",
            "--camera-index",
            "1",
            "--width",
            "320",
            "--height",
            "240",
            "--fps",
            "15",
            "--model-backend",
            "mock",
            "--pattern",
            "neutral",
            "--count",
            "2",
            "--no-show",
        ])

        self.assertEqual(args.source, "opencv_camera")
        self.assertEqual(args.camera_index, 1)
        self.assertEqual(args.width, 320)
        self.assertEqual(args.height, 240)
        self.assertEqual(args.fps, 15)

    def test_draw_overlay_accepts_fake_frame_and_returns_frame(self) -> None:
        frame = {"payload": object(), "width": 640, "height": 480}
        row = {key: None for key in STABLE_KEYS}
        row.update({
            "frame_id": 1,
            "emotion_tag": "tired",
            "confidence": 0.9,
            "fatigue_score": 0.85,
            "gate_triggered": True,
            "gate_reason": "high_fatigue",
            "latency_ms": 12.3,
        })
        fake_cv2 = types.SimpleNamespace(
            FONT_HERSHEY_SIMPLEX=0,
            putText=lambda image, *args, **kwargs: image,
        )

        result = probe_cv_gate.draw_overlay(frame, row, cv2_module=fake_cv2)

        self.assertIs(result, frame["payload"])

    async def test_opencv_camera_mock_no_show_with_mocked_source_finishes(self) -> None:
        args = probe_cv_gate.parse_args([
            "--source",
            "opencv_camera",
            "--camera-index",
            "0",
            "--model-backend",
            "mock",
            "--pattern",
            "neutral",
            "--count",
            "2",
            "--no-show",
        ])

        with patch("tools.probe_cv_gate.OpenCVCameraFrameSource", FakeOpenCVCameraFrameSource):
            with redirect_stdout(io.StringIO()):
                rows = await probe_cv_gate.probe_cv_gate(args)

        self.assertEqual(len(rows), 2)
        self.assertEqual([row["frame_source"] for row in rows], ["opencv_camera", "opencv_camera"])
        self.assertTrue(FakeOpenCVCameraFrameSource.closed)

    def test_camera_open_failure_returns_user_level_error(self) -> None:
        FakeOpenCVCameraFrameSource.raise_on_open = RuntimeError("Unable to open camera index 0.")
        with patch("tools.probe_cv_gate.OpenCVCameraFrameSource", FakeOpenCVCameraFrameSource):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
                exit_code = probe_cv_gate.main([
                    "--source",
                    "opencv_camera",
                    "--camera-index",
                    "0",
                    "--model-backend",
                    "mock",
                    "--pattern",
                    "neutral",
                    "--count",
                    "1",
                    "--no-show",
                ])

        self.assertEqual(exit_code, 1)
        self.assertIn("Unable to open camera index 0", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_parser_accepts_openvino_model_options(self) -> None:
        args = probe_cv_gate.parse_args([
            "--source",
            "opencv_camera",
            "--model-backend",
            "openvino",
            "--model-path",
            "base_station/models",
            "--device",
            "CPU",
            "--count",
            "2",
            "--no-show",
        ])

        self.assertEqual(args.model_backend, "openvino")
        self.assertEqual(args.model_path, "base_station/models")
        self.assertEqual(args.device, "CPU")

    def test_build_model_uses_openvino_face_emotion_model(self) -> None:
        args = probe_cv_gate.parse_args([
            "--model-backend",
            "openvino",
            "--model-path",
            "base_station/models",
            "--device",
            "AUTO",
        ])

        with patch("tools.probe_cv_gate.OpenVINOFaceEmotionModel", FakeOpenVINOFaceEmotionModel):
            model = probe_cv_gate.build_model(args)

        self.assertIsInstance(model, FakeOpenVINOFaceEmotionModel)
        self.assertEqual(model.model_path, "base_station/models")
        self.assertEqual(model.device, "AUTO")

    def test_openvino_output_normalizes_to_stable_probe_row(self) -> None:
        sample = {
            "emotion_tag": "tired",
            "cv_emotion_raw": "sadness",
            "confidence": 0.91,
            "fatigue_score": 0.82,
            "face_detected": True,
            "calibrated": False,
            "source": "openvino_face",
            "frame_source": "opencv_camera",
            "frame_id": 9,
            "timestamp_ms": 1234,
        }

        row = probe_cv_gate.normalize_probe_row(
            sample,
            {"should_trigger": True, "reason": "high_fatigue"},
            latency_ms=15.5,
        )

        self.assertTrue(STABLE_KEYS.issubset(row))
        self.assertEqual(row["source"], "openvino_face")
        self.assertEqual(row["cv_emotion_raw"], "sadness")
        self.assertEqual(row["face_detected"], True)
        self.assertEqual(row["gate_triggered"], True)
        self.assertEqual(row["gate_reason"], "high_fatigue")
        self.assertEqual(row["latency_ms"], 15.5)

    def test_openvino_model_init_failure_returns_user_level_error(self) -> None:
        FakeOpenVINOFaceEmotionModel.raise_on_init = FileNotFoundError("OpenVINO CV model(s) not found")
        with patch("tools.probe_cv_gate.OpenVINOFaceEmotionModel", FakeOpenVINOFaceEmotionModel):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
                exit_code = probe_cv_gate.main([
                    "--source",
                    "fake_camera",
                    "--model-backend",
                    "openvino",
                    "--model-path",
                    "missing-model-root",
                    "--device",
                    "CPU",
                    "--count",
                    "1",
                    "--no-show",
                ])

        self.assertEqual(exit_code, 1)
        self.assertIn("OpenVINO CV model", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
