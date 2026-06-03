"""Unit tests for FakeCameraFrameSource."""

from __future__ import annotations

import unittest

from base_station.perception.fake_camera import FakeCameraFrameSource


async def collect_frames(source: FakeCameraFrameSource) -> list[dict]:
    frames = []
    async for frame in source.frames():
        frames.append(frame)
    return frames


class FakeCameraFrameSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_count_limits_frame_output(self) -> None:
        frames = await collect_frames(FakeCameraFrameSource(count=3, interval_seconds=0))

        self.assertEqual(len(frames), 3)

    async def test_frame_id_increments_from_one(self) -> None:
        frames = await collect_frames(FakeCameraFrameSource(count=3, interval_seconds=0))

        self.assertEqual([frame["frame_id"] for frame in frames], [1, 2, 3])

    async def test_frame_contains_required_fields(self) -> None:
        frames = await collect_frames(FakeCameraFrameSource(count=1, interval_seconds=0))
        frame = frames[0]

        self.assertEqual(set(frame), {"source", "frame_id", "timestamp_ms", "width", "height", "payload"})
        self.assertEqual(frame["source"], "fake_camera")
        self.assertEqual(frame["width"], 640)
        self.assertEqual(frame["height"], 480)
        self.assertIsNone(frame["payload"])


if __name__ == "__main__":
    unittest.main()
