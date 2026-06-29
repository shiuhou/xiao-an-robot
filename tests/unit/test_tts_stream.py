"""Unit tests for base-station TTS PCM preparation."""

from __future__ import annotations

import struct
import unittest

from base_station.ws_server.tts_stream import limit_pcm_peak_s16le


class TtsStreamTest(unittest.TestCase):
    def test_limit_pcm_peak_scales_full_range_speech_to_speaker_safe_level(self) -> None:
        pcm = struct.pack("<hhhh", -32768, -16000, 1000, 32767)

        limited = limit_pcm_peak_s16le(pcm, target_peak=2800)
        samples = struct.unpack("<hhhh", limited)

        self.assertLessEqual(max(abs(sample) for sample in samples), 2800)
        self.assertGreater(abs(samples[3]), 2500)
        self.assertEqual(len(limited), len(pcm))

    def test_limit_pcm_peak_leaves_quiet_pcm_unchanged(self) -> None:
        pcm = struct.pack("<hhh", -1200, 0, 1500)

        self.assertEqual(limit_pcm_peak_s16le(pcm, target_peak=2800), pcm)

    def test_default_tts_peak_limit_is_conservative_for_amp_bringup(self) -> None:
        pcm = struct.pack("<hh", -32768, 32767)

        limited = limit_pcm_peak_s16le(pcm)
        samples = struct.unpack("<hh", limited)

        self.assertLessEqual(max(abs(sample) for sample in samples), 900)


if __name__ == "__main__":
    unittest.main()
