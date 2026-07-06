"""Unit tests for WebSocketVideoFrameSource."""

from __future__ import annotations

import asyncio
import unittest

import cv2
import numpy as np

from base_station.perception.ws_video_source import (
    VideoFrameDecodeError,
    WebSocketVideoFrameSource,
    WebSocketVideoObserverSource,
    decode_video_packet,
)

try:
    import websockets
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None


def make_packet(width: int = 320, height: int = 240, device_ts: int = 42) -> bytes:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    success, encoded = cv2.imencode(".jpg", image)
    if not success:
        raise AssertionError("JPEG test image encoding failed")

    jpeg_data = encoded.tobytes()
    return len(jpeg_data).to_bytes(4, "big") + device_ts.to_bytes(4, "big") + jpeg_data


class WebSocketVideoFrameSourceTest(unittest.IsolatedAsyncioTestCase):
    def test_decode_video_packet_returns_frame_dict(self) -> None:
        packet = make_packet(width=320, height=240, device_ts=42)

        frame = decode_video_packet(packet, frame_id=7)

        self.assertEqual(frame["source"], "ws_video")
        self.assertEqual(frame["frame_id"], 7)
        self.assertEqual(frame["device_timestamp"], 42)
        self.assertEqual(frame["width"], 320)
        self.assertEqual(frame["height"], 240)
        self.assertIsNotNone(frame["payload"])
        self.assertEqual(frame["payload"].shape[:2], (240, 320))

    def test_decode_rejects_short_packet(self) -> None:
        with self.assertRaises(VideoFrameDecodeError):
            decode_video_packet(b"short", frame_id=1)

    def test_decode_rejects_length_mismatch(self) -> None:
        packet = (100).to_bytes(4, "big") + (42).to_bytes(4, "big") + b"not-enough"

        with self.assertRaises(VideoFrameDecodeError):
            decode_video_packet(packet, frame_id=1)

    async def test_queue_drops_old_frame_when_full(self) -> None:
        source = WebSocketVideoFrameSource(maxsize=1)
        await source.push_packet(make_packet(device_ts=1))
        await source.push_packet(make_packet(device_ts=2))

        frames = source.frames()
        frame = await frames.__anext__()

        self.assertEqual(frame["device_timestamp"], 2)

    @unittest.skipIf(websockets is None, "websockets dependency is not installed")
    async def test_observer_source_decodes_binary_packets(self) -> None:
        packet = make_packet(device_ts=88)

        async def handler(websocket):
            await websocket.send(packet)
            await websocket.close()

        server = await websockets.serve(handler, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        try:
            source = WebSocketVideoObserverSource(
                url=f"ws://{host}:{port}/video-observer",
                reconnect_delay_seconds=0.01,
            )
            frames = source.frames()
            frame = await asyncio.wait_for(frames.__anext__(), timeout=1.0)
        finally:
            server.close()
            await server.wait_closed()

        self.assertEqual(frame["source"], "ws_video_observer")
        self.assertEqual(frame["device_timestamp"], 88)


if __name__ == "__main__":
    unittest.main()
