"""Unit tests for OpenCVCameraFrameSource."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from base_station.perception.opencv_camera import OpenCVCameraFrameSource


class FakeFrame:
    def __init__(self, width: int = 320, height: int = 240):
        self.shape = (height, width, 3)


class FakeCapture:
    opened = True
    read_success = True
    instances: list["FakeCapture"] = []

    def __init__(self, camera_index: int):
        self.camera_index = camera_index
        self.set_calls: list[tuple[int, int]] = []
        self.released = False
        FakeCapture.instances.append(self)

    def set(self, prop: int, value: int) -> None:
        self.set_calls.append((prop, value))

    def isOpened(self) -> bool:
        return self.opened

    def read(self) -> tuple[bool, FakeFrame | None]:
        if not self.read_success:
            return False, None
        return True, FakeFrame()

    def release(self) -> None:
        self.released = True


def fake_cv2_module() -> types.SimpleNamespace:
    FakeCapture.opened = True
    FakeCapture.read_success = True
    FakeCapture.instances = []
    return types.SimpleNamespace(
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        VideoCapture=FakeCapture,
    )


class OpenCVCameraFrameSourceTest(unittest.TestCase):
    def test_open_creates_video_capture_and_sets_size(self) -> None:
        fake_cv2 = fake_cv2_module()
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            source = OpenCVCameraFrameSource(camera_index=1, width=800, height=600)
            source.open()

        capture = FakeCapture.instances[0]
        self.assertEqual(capture.camera_index, 1)
        self.assertEqual(capture.set_calls, [(3, 800), (4, 600)])

    def test_read_frame_returns_required_fields(self) -> None:
        fake_cv2 = fake_cv2_module()
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            source = OpenCVCameraFrameSource()
            frame = source.read_frame()

        self.assertEqual(set(frame), {"source", "frame_id", "timestamp_ms", "width", "height", "payload"})
        self.assertEqual(frame["source"], "opencv_camera")
        self.assertEqual(frame["frame_id"], 1)
        self.assertIsInstance(frame["timestamp_ms"], int)
        self.assertEqual(frame["width"], 320)
        self.assertEqual(frame["height"], 240)
        self.assertIsInstance(frame["payload"], FakeFrame)

    def test_frame_id_increments_across_reads(self) -> None:
        fake_cv2 = fake_cv2_module()
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            source = OpenCVCameraFrameSource()
            first = source.read_frame()
            second = source.read_frame()

        self.assertEqual(first["frame_id"], 1)
        self.assertEqual(second["frame_id"], 2)

    def test_close_releases_capture(self) -> None:
        fake_cv2 = fake_cv2_module()
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            source = OpenCVCameraFrameSource()
            source.open()
            capture = FakeCapture.instances[0]
            source.close()

        self.assertTrue(capture.released)

    def test_context_manager_closes_capture(self) -> None:
        fake_cv2 = fake_cv2_module()
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            with OpenCVCameraFrameSource() as source:
                capture = source._capture

        self.assertTrue(capture.released)

    def test_open_raises_when_camera_cannot_open(self) -> None:
        fake_cv2 = fake_cv2_module()
        FakeCapture.opened = False
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            source = OpenCVCameraFrameSource(camera_index=2)
            with self.assertRaisesRegex(RuntimeError, "unable to open camera index 2"):
                source.open()

        self.assertTrue(FakeCapture.instances[0].released)

    def test_read_frame_raises_when_read_fails(self) -> None:
        fake_cv2 = fake_cv2_module()
        FakeCapture.read_success = False
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            source = OpenCVCameraFrameSource()
            with self.assertRaisesRegex(RuntimeError, "Failed to read frame"):
                source.read_frame()

    def test_missing_cv2_raises_clear_import_error(self) -> None:
        with patch.dict(sys.modules, {"cv2": None}):
            source = OpenCVCameraFrameSource()
            with self.assertRaisesRegex(ImportError, "opencv-python"):
                source.open()


if __name__ == "__main__":
    unittest.main()
