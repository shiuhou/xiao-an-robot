"""OpenCV camera frame source.

This module intentionally delays importing cv2 until the camera is opened so
projects without opencv-python installed can still run the rest of the tests.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from base_station.perception.frame_source import FrameSource


class OpenCVCameraFrameSource(FrameSource):
    """Read camera frames with cv2.VideoCapture."""

    def __init__(
        self,
        camera_index: int = 0,
        width: int | None = None,
        height: int | None = None,
    ):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self._capture: Any | None = None
        self._frame_id = 0

    def open(self) -> None:
        """Open the camera device."""
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError("OpenCVCameraFrameSource requires opencv-python to be installed.") from exc

        capture = cv2.VideoCapture(self.camera_index)
        if self.width is not None:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height is not None:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Unable to open camera index {self.camera_index}.")

        self._capture = capture

    def read_frame(self) -> dict:
        """Read one frame and return the project frame dictionary."""
        if self._capture is None:
            self.open()

        success, frame = self._capture.read()
        if not success:
            raise RuntimeError("Failed to read frame from OpenCV camera.")

        self._frame_id += 1
        frame_height, frame_width = self._get_frame_size(frame)
        return {
            "source": "opencv_camera",
            "frame_id": self._frame_id,
            "timestamp_ms": int(time.time() * 1000),
            "width": frame_width,
            "height": frame_height,
            "payload": frame,
        }

    async def frames(self) -> AsyncIterator[dict]:
        """Yield frames until the caller stops the async iterator."""
        try:
            while True:
                yield self.read_frame()
                await asyncio.sleep(0)
        finally:
            self.close()

    def close(self) -> None:
        """Release the camera device if it is open."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> "OpenCVCameraFrameSource":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @staticmethod
    def _get_frame_size(frame: Any) -> tuple[int, int]:
        shape = getattr(frame, "shape", None)
        if not shape or len(shape) < 2:
            raise RuntimeError("OpenCV frame does not expose a valid shape.")
        return int(shape[0]), int(shape[1])
