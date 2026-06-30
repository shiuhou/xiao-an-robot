"""Unit tests for fixed-window continuous ASR demo helpers."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from base_station.monitor.continuous_asr_demo import (
    TailEnergyReader,
    UtteranceDetector,
)


class ContinuousAsrDemoTest(unittest.TestCase):
    def test_utterance_detector_emits_once_after_silence(self) -> None:
        detector = UtteranceDetector(
            trigger_rms_dbfs=-42.0,
            release_rms_dbfs=-48.0,
            silence_ms=600,
            min_speech_ms=300,
            cooldown_ms=500,
        )

        self.assertIsNone(detector.update(now_ms=0, rms_dbfs=-55.0))
        self.assertIsNone(detector.update(now_ms=100, rms_dbfs=-35.0))
        self.assertIsNone(detector.update(now_ms=300, rms_dbfs=-34.0))
        self.assertIsNone(detector.update(now_ms=500, rms_dbfs=-50.0))
        event = detector.update(now_ms=900, rms_dbfs=-51.0)

        self.assertIsNotNone(event)
        self.assertEqual(event["start_ms"], 100)
        self.assertEqual(event["end_ms"], 900)
        self.assertEqual(event["duration_ms"], 800)

        self.assertIsNone(detector.update(now_ms=1200, rms_dbfs=-35.0))
        self.assertIsNone(detector.update(now_ms=1500, rms_dbfs=-52.0))

    def test_utterance_detector_rejects_short_impulse(self) -> None:
        detector = UtteranceDetector(
            trigger_rms_dbfs=-42.0,
            release_rms_dbfs=-48.0,
            silence_ms=300,
            min_speech_ms=500,
        )

        detector.update(now_ms=0, rms_dbfs=-35.0)
        event = detector.update(now_ms=350, rms_dbfs=-55.0)

        self.assertIsNone(event)

    def test_tail_energy_reader_uses_recent_pcm_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pcm_path = Path(temp_dir) / "latest_audio.pcm"
            quiet = [0] * 1600
            loud_tail = [8000] * 1600
            pcm_path.write_bytes(struct.pack("<" + "h" * 3200, *(quiet + loud_tail)))

            reader = TailEnergyReader(pcm_path, sample_rate=16000, tail_ms=100)
            stats = reader.read_tail_stats()

        self.assertGreater(stats["rms_dbfs"], -13.0)
        self.assertLess(stats["rms_dbfs"], -11.0)
        self.assertGreater(stats["peak_dbfs"], -13.0)
        self.assertLess(stats["peak_dbfs"], -11.0)


if __name__ == "__main__":
    unittest.main()
