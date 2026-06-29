"""Unit tests for the base station /audio WebSocket channel."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    import websockets  # noqa: F401
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None

if websockets is not None:
    from base_station.ws_server import server as ws_server
else:  # pragma: no cover - import is skipped with the dependency
    ws_server = None


def build_message(msg_type: str, seq: int, payload: dict) -> str:
    return json.dumps({
        "type": msg_type,
        "ts": 1714539000000 + seq,
        "seq": seq,
        "payload": payload,
    }, ensure_ascii=False)


class FakeAudioWebSocket:
    def __init__(self, messages: list[bytes | str]):
        self.messages = messages
        self.sent: list[str] = []

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def send(self, message: str) -> None:
        self.sent.append(message)


@unittest.skipIf(websockets is None, "websockets dependency is not installed")
class WebSocketAudioChannelTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ws_server.reset_state_for_tests()
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    async def asyncTearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()
        ws_server.reset_state_for_tests()

    async def test_handle_audio_writes_latest_pcm_and_stats_for_binary_frames(self) -> None:
        first = b"\x01\x00\x02\x00"
        second = b"\x03\x00\x04\x00\x05\x00"
        websocket = FakeAudioWebSocket([first, "ignore-text", second])

        await ws_server.handle_audio(websocket)

        latest_pcm = Path("runtime") / "latest_audio.pcm"
        stats_path = Path("runtime") / "audio_stats.json"
        self.assertEqual(latest_pcm.read_bytes(), first + second)

        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        self.assertEqual(stats["format"], "pcm_s16le")
        self.assertEqual(stats["sample_rate"], 16000)
        self.assertEqual(stats["channels"], 1)
        self.assertEqual(stats["chunks"], 2)
        self.assertEqual(stats["bytes"], len(first) + len(second))
        self.assertEqual(stats["latest_chunk_bytes"], len(second))
        self.assertLessEqual(stats["latest_file_bytes"], stats["latest_file_max_bytes"])
        self.assertEqual(stats["latest_window"]["sample_rate"], 16000)
        self.assertEqual(stats["latest_window"]["sample_count"], 5)
        self.assertEqual(stats["latest_window"]["peak"], 5)
        self.assertEqual(stats["latest_window"]["clipping_samples"], 0)

    async def test_handle_control_accepts_audio_chunk_meta_without_warning(self) -> None:
        websocket = FakeAudioWebSocket([
            build_message(
                "device.hello",
                1,
                {"device_id": "audio-test-robot", "firmware": "unit-test", "battery": 90},
            ),
            build_message(
                "audio.chunk_meta",
                2,
                {
                    "device_id": "audio-test-robot",
                    "format": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "chunk_id": 7,
                },
            ),
        ])

        with self.assertNoLogs("ws_server", level="WARNING"):
            await ws_server.handle_control(websocket)

        stats = json.loads((Path("runtime") / "audio_stats.json").read_text(encoding="utf-8"))
        self.assertEqual(stats["last_chunk_id"], 7)
        self.assertEqual(stats["last_meta"]["format"], "pcm_s16le")


if __name__ == "__main__":
    unittest.main()
