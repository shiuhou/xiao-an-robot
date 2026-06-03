"""Fake camera frame source for local perception pipeline tests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from base_station.perception.frame_source import FrameSource


class FakeCameraFrameSource(FrameSource):
    """Generate deterministic camera-like frame dictionaries."""

    def __init__(
        self,
        count: int | None = 5,
        interval_seconds: float = 1.0,
        width: int = 640,
        height: int = 480,
    ):
        self.count = count
        self.interval_seconds = interval_seconds
        self.width = width
        self.height = height

    async def frames(self) -> AsyncIterator[dict]:
        index = 0
        while self.count is None or index < self.count:
            frame_id = index + 1
            yield {
                "source": "fake_camera",
                "frame_id": frame_id,
                "timestamp_ms": int(time.time() * 1000),
                "width": self.width,
                "height": self.height,
                "payload": None,
            }
            index += 1
            if self.interval_seconds > 0:
                await asyncio.sleep(self.interval_seconds)
