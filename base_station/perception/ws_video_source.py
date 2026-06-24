"""WebSocket JPEG frame source for ESP32 /video packets."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

import cv2
import numpy as np

from base_station.perception.frame_source import FrameSource


class VideoFrameDecodeError(ValueError):
    """Raised when a /video binary packet cannot be decoded into a frame."""


def decode_video_packet(packet: bytes, frame_id: int) -> dict:
    """Decode one ESP32 /video binary packet into a camera-like frame dict."""
    try:
        packet_view = memoryview(packet)
    except TypeError as exc:
        raise VideoFrameDecodeError("video packet must be bytes-like") from exc

    if len(packet_view) < 8:
        raise VideoFrameDecodeError("video packet is shorter than the 8-byte header")

    jpeg_len = int.from_bytes(packet_view[0:4], "big")
    device_ts = int.from_bytes(packet_view[4:8], "big")
    if jpeg_len <= 0:
        raise VideoFrameDecodeError("JPEG length must be positive")

    jpeg_data = packet_view[8 : 8 + jpeg_len]
    if len(jpeg_data) != jpeg_len:
        raise VideoFrameDecodeError("JPEG payload length does not match header")

    encoded = np.frombuffer(jpeg_data, dtype=np.uint8)
    frame_bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame_bgr is None:
        raise VideoFrameDecodeError("JPEG payload could not be decoded")

    height, width = frame_bgr.shape[:2]
    return {
        "source": "ws_video",
        "frame_id": frame_id,
        "timestamp_ms": int(time.time() * 1000),
        "device_timestamp": device_ts,
        "width": width,
        "height": height,
        "payload": frame_bgr,
    }


class WebSocketVideoFrameSource(FrameSource):
    """Queue-backed frame source for decoded WebSocket /video frames."""

    def __init__(self, maxsize: int = 2):
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=maxsize)
        self._next_frame_id = 1

    async def push_packet(self, packet: bytes) -> dict:
        frame = decode_video_packet(packet, self._next_frame_id)
        self._next_frame_id += 1
        await self.push_frame(frame)
        return frame

    async def push_frame(self, frame: dict) -> None:
        while self._queue.full():
            self._queue.get_nowait()
        await self._queue.put(frame)

    async def frames(self) -> AsyncIterator[dict]:
        while True:
            yield await self._queue.get()
