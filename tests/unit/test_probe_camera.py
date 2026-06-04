"""Unit tests for tools.probe_camera."""

from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from tools import probe_camera


class FakeOpenCVCameraFrameSource:
    frames_read = 0
    raise_on_enter: Exception | None = None

    def __init__(
        self,
        camera_index: int = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.closed = False

    def __enter__(self) -> "FakeOpenCVCameraFrameSource":
        if self.raise_on_enter is not None:
            raise self.raise_on_enter
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.closed = True

    def read_frame(self) -> dict:
        type(self).frames_read += 1
        return {
            "source": "opencv_camera",
            "frame_id": type(self).frames_read,
            "timestamp_ms": 1000 + type(self).frames_read,
            "width": self.width or 640,
            "height": self.height or 480,
            "payload": f"frame-{type(self).frames_read}",
        }


class ProbeCameraTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeOpenCVCameraFrameSource.frames_read = 0
        FakeOpenCVCameraFrameSource.raise_on_enter = None

    def make_args(self, count: int = 3, interval: float = 0.0) -> argparse.Namespace:
        return argparse.Namespace(
            camera_index=0,
            camera_width=320,
            camera_height=240,
            count=count,
            interval=interval,
            verbose=False,
        )

    def test_probe_camera_reads_requested_count(self) -> None:
        with patch("tools.probe_camera.OpenCVCameraFrameSource", FakeOpenCVCameraFrameSource):
            with redirect_stdout(io.StringIO()):
                summary = probe_camera.probe_camera(self.make_args(count=3))

        self.assertEqual(FakeOpenCVCameraFrameSource.frames_read, 3)
        self.assertEqual(summary["total_frames"], 3)
        self.assertEqual(summary["width"], 320)
        self.assertEqual(summary["height"], 240)

    def test_build_summary_calculates_total_frames_and_fps(self) -> None:
        frames = [
            {"width": 640, "height": 480},
            {"width": 640, "height": 480},
        ]

        summary = probe_camera.build_summary(frames, duration_seconds=0.5)

        self.assertEqual(summary["total_frames"], 2)
        self.assertEqual(summary["approx_fps"], 4.0)

    def test_main_returns_nonzero_for_import_error(self) -> None:
        FakeOpenCVCameraFrameSource.raise_on_enter = ImportError("opencv-python is required")
        with patch("tools.probe_camera.OpenCVCameraFrameSource", FakeOpenCVCameraFrameSource):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
                exit_code = probe_camera.main(["--count", "1", "--interval", "0"])

        self.assertEqual(exit_code, 1)
        self.assertIn("opencv-python", stderr.getvalue())

    def test_main_returns_nonzero_for_runtime_error(self) -> None:
        FakeOpenCVCameraFrameSource.raise_on_enter = RuntimeError("Unable to open camera index 0")
        with patch("tools.probe_camera.OpenCVCameraFrameSource", FakeOpenCVCameraFrameSource):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
                exit_code = probe_camera.main(["--count", "1", "--interval", "0"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Unable to open camera index 0", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
