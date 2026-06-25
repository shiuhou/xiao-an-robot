"""Unit tests for wiring /video packets into WebSocketVideoFrameSource."""

from __future__ import annotations

import unittest
import asyncio

import cv2
import numpy as np

try:
    import websockets  # noqa: F401
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None

if websockets is not None:
    from base_station.perception.ws_video_source import WebSocketVideoFrameSource
    from base_station.ws_server import server as ws_server
else:  # pragma: no cover - import is skipped with the dependency
    WebSocketVideoFrameSource = None
    ws_server = None


def make_video_packet(width: int = 320, height: int = 240, device_ts: int = 42) -> bytes:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    success, encoded = cv2.imencode(".jpg", image)
    if not success:
        raise AssertionError("JPEG test image encoding failed")

    jpeg_data = encoded.tobytes()
    return len(jpeg_data).to_bytes(4, "big") + device_ts.to_bytes(4, "big") + jpeg_data


class FakeVideoWebSocket:
    def __init__(self, messages: list[bytes]):
        self.messages = messages

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)


@unittest.skipIf(websockets is None, "websockets dependency is not installed")
class WebSocketServerVideoSourceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ws_server.reset_state_for_tests()

    async def asyncTearDown(self) -> None:
        ws_server.reset_state_for_tests()

    async def test_handle_video_pushes_binary_packet_to_injected_source(self) -> None:
        source = WebSocketVideoFrameSource(maxsize=1)
        ws_server.set_video_frame_source(source)
        websocket = FakeVideoWebSocket([make_video_packet(device_ts=1234)])

        await ws_server.handle_video(websocket)
        frames = source.frames()
        frame = await frames.__anext__()

        self.assertEqual(frame["source"], "ws_video")
        self.assertEqual(frame["width"], 320)
        self.assertEqual(frame["height"], 240)
        self.assertEqual(frame["device_timestamp"], 1234)

    async def test_handle_video_accepts_split_header_and_jpeg_frames(self) -> None:
        source = WebSocketVideoFrameSource(maxsize=1)
        ws_server.set_video_frame_source(source)
        packet = make_video_packet(device_ts=5678)
        websocket = FakeVideoWebSocket([packet[:8], packet[8:]])

        await ws_server.handle_video(websocket)
        frames = source.frames()
        frame = await asyncio.wait_for(frames.__anext__(), timeout=0.2)

        self.assertEqual(frame["source"], "ws_video")
        self.assertEqual(frame["width"], 320)
        self.assertEqual(frame["height"], 240)
        self.assertEqual(frame["device_timestamp"], 5678)

    async def test_handle_video_without_source_does_not_crash(self) -> None:
        ws_server.set_video_frame_source(None)
        websocket = FakeVideoWebSocket([make_video_packet(device_ts=1234)])

        await ws_server.handle_video(websocket)

    async def test_handle_video_invalid_packet_does_not_crash(self) -> None:
        source = WebSocketVideoFrameSource(maxsize=1)
        ws_server.set_video_frame_source(source)
        websocket = FakeVideoWebSocket([b"bad"])

        await ws_server.handle_video(websocket)


if __name__ == "__main__":
    unittest.main()
