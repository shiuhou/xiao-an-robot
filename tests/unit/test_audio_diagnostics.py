"""Unit tests for raw PCM microphone diagnostics."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from base_station.perception.audio_diagnostics import (
    diagnose_pcm_file,
    pcm_s16le_stats,
    write_pcm_s16le_wav,
)


class AudioDiagnosticsTest(unittest.TestCase):
    def test_pcm_s16le_stats_reports_level_dc_and_clipping(self) -> None:
        pcm = struct.pack("<hhhh", -32768, -1000, 1000, 32767)

        stats = pcm_s16le_stats(pcm, sample_rate=16000, channels=1)

        self.assertEqual(stats["format"], "pcm_s16le")
        self.assertEqual(stats["sample_rate"], 16000)
        self.assertEqual(stats["channels"], 1)
        self.assertEqual(stats["sample_count"], 4)
        self.assertEqual(stats["duration_ms"], 0.25)
        self.assertEqual(stats["peak"], 32768)
        self.assertAlmostEqual(stats["peak_dbfs"], 0.0, places=3)
        self.assertEqual(stats["clipping_samples"], 2)
        self.assertEqual(stats["clipping_percent"], 50.0)
        self.assertAlmostEqual(stats["dc_offset"], -0.25, places=2)
        self.assertLess(stats["rms_dbfs"], 0.0)

    def test_diagnose_pcm_file_writes_wav_and_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pcm_path = Path(temp_dir) / "latest_audio.pcm"
            wav_path = Path(temp_dir) / "mic_20cm.wav"
            report_path = Path(temp_dir) / "mic_20cm.json"
            pcm_path.write_bytes(struct.pack("<hhhh", 0, 16000, -16000, 0))

            report = diagnose_pcm_file(
                pcm_path,
                wav_path=wav_path,
                report_path=report_path,
                sample_rate=16000,
                channels=1,
            )

            self.assertEqual(report["source_pcm"], str(pcm_path))
            self.assertEqual(report["wav_path"], str(wav_path))
            self.assertTrue(wav_path.exists())
            saved_report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_report["sample_count"], 4)

            with wave.open(str(wav_path), "rb") as wav:
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.readframes(4), pcm_path.read_bytes())

    def test_write_pcm_s16le_wav_rejects_odd_byte_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "even number of bytes"):
                write_pcm_s16le_wav(
                    b"\x00",
                    Path(temp_dir) / "bad.wav",
                    sample_rate=16000,
                    channels=1,
                )


if __name__ == "__main__":
    unittest.main()
