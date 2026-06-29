"""Unit tests for base-station TTS PCM streaming pacing."""

from __future__ import annotations

import unittest

from base_station.ws_server import server as ws_server


class FakeControlWebSocket:
    def __init__(self) -> None:
        self.sent: list[bytes | str] = []

    async def send(self, message: bytes | str) -> None:
        self.sent.append(message)


class WebSocketTtsStreamTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ws_server.reset_state_for_tests()

    async def asyncTearDown(self) -> None:
        ws_server.reset_state_for_tests()

    async def test_control_pcm_stream_is_paced_to_audio_duration(self) -> None:
        websocket = FakeControlWebSocket()
        ws_server.sessions["speaker-test"] = {"ws": websocket}
        stream = ws_server.TtsPcmStream(
            audio_id="tts-paced",
            text_preview="hello",
            pcm=b"\x01\x00" * 2048,
            sample_rate=16000,
            channels=1,
        )

        original_chunk_bytes = ws_server.CONTROL_TTS_CHUNK_BYTES
        original_sleep = ws_server.asyncio.sleep
        sleeps: list[float] = []

        async def fake_sleep(duration: float) -> None:
            sleeps.append(duration)

        ws_server.CONTROL_TTS_CHUNK_BYTES = 2048
        ws_server.asyncio.sleep = fake_sleep
        try:
            ok, error = await ws_server.stream_control_binary_to_robot(stream, "speaker-test")
        finally:
            ws_server.CONTROL_TTS_CHUNK_BYTES = original_chunk_bytes
            ws_server.asyncio.sleep = original_sleep

        self.assertTrue(ok, error)
        self.assertIsNone(error)
        self.assertEqual(len([msg for msg in websocket.sent if isinstance(msg, bytes)]), 2)
        self.assertEqual(len(sleeps), 3)
        self.assertTrue(all(duration > 0 for duration in sleeps))
        self.assertAlmostEqual(sleeps[0], ws_server.CONTROL_TTS_START_DELAY_SECONDS, places=3)
        self.assertAlmostEqual(sleeps[1], 0.064, places=3)
        self.assertIn("audio.stream_end", websocket.sent[-1])

    def test_control_tts_chunks_stay_small_for_firmware_callback_latency(self) -> None:
        self.assertLessEqual(ws_server.CONTROL_TTS_CHUNK_BYTES, 512)


if __name__ == "__main__":
    unittest.main()
