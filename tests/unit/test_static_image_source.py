"""Unit tests for StaticImageFrameSource."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from base_station.perception.static_image_source import StaticImageFrameSource


async def collect_frames(source: StaticImageFrameSource) -> list[dict]:
    frames = []
    async for frame in source.frames():
        frames.append(frame)
    return frames


def write_test_png(path: Path) -> None:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:
        raise unittest.SkipTest(f"OpenCV/numpy not available for image fixture: {exc}") from exc

    image = np.zeros((1, 1, 3), dtype=np.uint8)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"failed to write test image: {path}")


class StaticImageFrameSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_reads_png_into_camera_like_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "image.png"
            write_test_png(path)

            frames = await collect_frames(StaticImageFrameSource(path, count=1))

        self.assertEqual(len(frames), 1)
        frame = frames[0]
        self.assertEqual(set(frame), {"source", "frame_id", "timestamp_ms", "width", "height", "payload"})
        self.assertEqual(frame["source"], "image_file")
        self.assertEqual(frame["frame_id"], 1)
        self.assertEqual(frame["width"], 1)
        self.assertEqual(frame["height"], 1)
        self.assertIsNotNone(frame["payload"])

    async def test_missing_file_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.png"
            source = StaticImageFrameSource(path, count=1)

            with self.assertRaisesRegex(FileNotFoundError, "Static image path does not exist"):
                source.read_frame()

    async def test_undecodable_file_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.jpg"
            path.write_text("not an image", encoding="utf-8")
            source = StaticImageFrameSource(path, count=1)

            with self.assertRaisesRegex(ValueError, "Failed to decode static image"):
                source.read_frame()

    async def test_unsupported_extension_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "image.gif"
            write_test_png(path)
            source = StaticImageFrameSource(path, count=1)

            with self.assertRaisesRegex(ValueError, "PNG/JPG/JPEG"):
                source.read_frame()


if __name__ == "__main__":
    unittest.main()
