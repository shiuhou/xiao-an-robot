"""Unit tests for base-station TTS PCM streaming pacing."""

from __future__ import annotations

import unittest
from unittest import mock

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

    async def test_control_pcm_stream_is_paced_slightly_ahead_of_audio_duration(self) -> None:
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
        self.assertGreaterEqual(ws_server.CONTROL_TTS_START_DELAY_SECONDS, 1.0)
        self.assertAlmostEqual(sleeps[0], ws_server.CONTROL_TTS_START_DELAY_SECONDS, places=3)
        self.assertAlmostEqual(
            sleeps[1],
            0.064 * ws_server.CONTROL_TTS_CHUNK_PACE_RATIO,
            places=3,
        )
        self.assertIn("audio.stream_end", websocket.sent[-1])

    def test_control_tts_chunks_fit_firmware_pcm_queue_budget(self) -> None:
        self.assertLessEqual(ws_server.CONTROL_TTS_CHUNK_BYTES, 2048)
        self.assertGreater(ws_server.CONTROL_TTS_CHUNK_PACE_RATIO, 0.75)
        self.assertLess(ws_server.CONTROL_TTS_CHUNK_PACE_RATIO, 1.0)

    def test_control_tts_stream_defaults_to_configured_backend(self) -> None:
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch("base_station.ws_server.server.external_tts_backend_configured", return_value=True),
        ):
            self.assertTrue(ws_server.control_tts_stream_enabled())

    def test_control_tts_stream_can_be_explicitly_disabled(self) -> None:
        with (
            mock.patch.dict("os.environ", {ws_server.CONTROL_TTS_STREAM_ENV: "0"}, clear=True),
            mock.patch("base_station.ws_server.server.external_tts_backend_configured", return_value=True),
        ):
            self.assertFalse(ws_server.control_tts_stream_enabled())

    def test_tts_runtime_settings_expose_clear_speaker_baseline(self) -> None:
        with mock.patch.dict("os.environ", {
            ws_server.CONTROL_TTS_STREAM_ENV: "1",
            "XIAOAN_TTS_TARGET_PEAK": "500",
        }, clear=True):
            settings = ws_server.tts_runtime_settings()

        self.assertTrue(settings["control_stream_enabled"])
        self.assertEqual(settings["target_peak"], 500)
        self.assertEqual(settings["chunk_bytes"], 2048)
        self.assertEqual(settings["start_delay_seconds"], 1.2)
        self.assertEqual(settings["pace_ratio"], 0.85)
        self.assertEqual(settings["pcm_format"], "pcm_s16le")
        self.assertEqual(settings["sample_rate"], 16000)
        self.assertEqual(settings["channels"], 1)
        self.assertEqual(settings["playback_mode_expected"], "buffered_after_stream_end")

    async def test_tts_synthesis_runs_off_event_loop_thread(self) -> None:
        expected_stream = ws_server.TtsPcmStream(
            audio_id="tts-threaded",
            text_preview="hello",
            pcm=b"\x01\x00",
            sample_rate=16000,
            channels=1,
        )
        calls: list[tuple[object, str]] = []

        async def fake_to_thread(func, text):
            calls.append((func, text))
            return expected_stream

        with mock.patch("base_station.ws_server.server.asyncio.to_thread", side_effect=fake_to_thread):
            stream = await ws_server.synthesize_tts_pcm_stream_async("hello")

        self.assertIs(stream, expected_stream)
        self.assertEqual(calls, [(ws_server.synthesize_tts_pcm_stream, "hello")])


if __name__ == "__main__":
    unittest.main()
