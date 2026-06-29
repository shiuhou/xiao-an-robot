"""Unit tests for speech-window extraction before ASR."""

from __future__ import annotations

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from base_station.perception.audio_segments import trim_wav_to_speech


def write_test_wav(path: Path, samples: list[int], sample_rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack("<" + "h" * len(samples), *samples))


class AudioSegmentsTest(unittest.TestCase):
    def test_trim_wav_to_speech_keeps_speech_with_padding(self) -> None:
        sample_rate = 16000
        quiet = [0] * sample_rate
        speech = [
            int(9000 * math.sin(2 * math.pi * 440 * i / sample_rate))
            for i in range(sample_rate // 2)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "window.wav"
            trimmed = Path(temp_dir) / "trimmed.wav"
            write_test_wav(source, quiet + speech + quiet, sample_rate=sample_rate)

            result = trim_wav_to_speech(
                source,
                trimmed,
                threshold=0.02,
                frame_ms=20,
                padding_ms=100,
            )

            self.assertTrue(result["speech_detected"])
            self.assertEqual(result["source_path"], str(source))
            self.assertEqual(result["trimmed_path"], str(trimmed))
            self.assertGreaterEqual(result["start_ms"], 880)
            self.assertLessEqual(result["start_ms"], 1000)
            self.assertGreaterEqual(result["end_ms"], 1500)
            self.assertLessEqual(result["end_ms"], 1640)
            self.assertGreaterEqual(result["duration_ms"], 600)
            self.assertLessEqual(result["duration_ms"], 760)

            with wave.open(str(trimmed), "rb") as wav:
                self.assertEqual(wav.getframerate(), sample_rate)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertGreater(wav.getnframes(), sample_rate // 2)
                self.assertLess(wav.getnframes(), sample_rate)

    def test_trim_wav_to_speech_reports_no_speech_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "quiet.wav"
            trimmed = Path(temp_dir) / "trimmed.wav"
            write_test_wav(source, [0] * 16000)

            result = trim_wav_to_speech(source, trimmed, threshold=0.02)

            self.assertFalse(result["speech_detected"])
            self.assertFalse(trimmed.exists())


if __name__ == "__main__":
    unittest.main()
