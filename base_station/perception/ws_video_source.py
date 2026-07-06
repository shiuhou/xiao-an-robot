"""WebSocket JPEG frame source for ESP32 /video packets."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

import cv2
import numpy as np

from base_station.perception.frame_source import FrameSource

logger = logging.getLogger(__name__)


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


class WebSocketVideoObserverSource(FrameSource):
    """Frame source that subscribes to the base-station /video-observer stream."""

    def __init__(
        self,
        url: str = "ws://127.0.0.1:8765/video-observer",
        *,
        reconnect_delay_seconds: float = 1.0,
        open_timeout_seconds: float = 3.0,
    ):
        self.url = url
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self.open_timeout_seconds = open_timeout_seconds
        self._next_frame_id = 1

    async def frames(self) -> AsyncIterator[dict]:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(f"missing websockets dependency: {exc}") from exc

        while True:
            try:
                async with websockets.connect(
                    self.url,
                    open_timeout=self.open_timeout_seconds,
                ) as websocket:
                    async for message in websocket:
                        if not isinstance(message, bytes):
                            continue
                        try:
                            frame = decode_video_packet(message, self._next_frame_id)
                        except VideoFrameDecodeError as exc:
                            logger.warning("Invalid /video-observer frame: %s", exc)
                            continue
                        self._next_frame_id += 1
                        frame["source"] = "ws_video_observer"
                        yield frame
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Video observer disconnected from %s: %s", self.url, exc)
                await asyncio.sleep(self.reconnect_delay_seconds)
