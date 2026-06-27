"""Unit tests for VAD interface placeholders."""

from __future__ import annotations

import unittest

from base_station.perception.vad import (
    EnergyVADBackend,
    FakeVADBackend,
    FakeVoiceActivityDetector,
    SileroVADBackend,
    SileroVoiceActivityDetector,
    VoiceActivityDetector,
    VoiceActivitySource,
)


class VoiceActivityDetectorTest(unittest.TestCase):
    def test_fake_vad_returns_pattern_values_in_order(self) -> None:
        detector = FakeVoiceActivityDetector(pattern=[True, False, True])

        self.assertTrue(detector.is_speech(b"frame"))
        self.assertFalse(detector.is_speech(b"frame"))
        self.assertTrue(detector.is_speech(b"frame"))

    def test_fake_vad_returns_false_after_pattern_exhausted(self) -> None:
        detector = FakeVoiceActivityDetector(pattern=[True])

        self.assertTrue(detector.is_speech(b"frame"))
        self.assertFalse(detector.is_speech(b"frame"))

    def test_fake_vad_without_pattern_returns_false(self) -> None:
        detector = FakeVoiceActivityDetector()

        self.assertFalse(detector.is_speech(b"frame"))

    def test_base_voice_activity_source_raises_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            VoiceActivitySource().is_speech(b"frame")

    def test_silero_placeholder_saves_configuration(self) -> None:
        detector = SileroVoiceActivityDetector(model_path="models/silero.onnx", threshold=0.7)

        self.assertEqual(detector.model_path, "models/silero.onnx")
        self.assertEqual(detector.threshold, 0.7)

    def test_silero_is_speech_raises_not_implemented(self) -> None:
        detector = SileroVoiceActivityDetector(model_path="models/silero.onnx")

        with self.assertRaisesRegex(NotImplementedError, "Silero-VAD is not implemented yet"):
            detector.is_speech(b"frame")

    def test_legacy_voice_activity_detector_keeps_model_path_and_raises(self) -> None:
        detector = VoiceActivityDetector(model_path="models/silero.onnx", threshold=0.6)

        self.assertEqual(detector.model_path, "models/silero.onnx")
        self.assertEqual(detector.threshold, 0.6)
        with self.assertRaises(NotImplementedError):
            detector.is_speech(b"frame")

    def test_fake_vad_backend_speech_contract(self) -> None:
        result = FakeVADBackend(pattern="speech").analyze({"duration_ms": 1234})

        self.assertTrue(result["speech_detected"])
        self.assertEqual(result["reason"], "fake_speech")
        self.assertEqual(result["end_ms"], 1234)

    def test_fake_vad_backend_silence_contract(self) -> None:
        result = FakeVADBackend(pattern="silence").analyze({"duration_ms": 1234})

        self.assertFalse(result["speech_detected"])
        self.assertEqual(result["reason"], "fake_silence")

    def test_energy_vad_detects_silence(self) -> None:
        result = EnergyVADBackend().analyze({
            "pcm_bytes": b"\x00\x00" * 160,
            "sample_width": 2,
            "channels": 1,
            "duration_ms": 10,
        })

        self.assertFalse(result["speech_detected"])
        self.assertEqual(result["reason"], "energy_threshold")

    def test_silero_backend_missing_model_raises_clear_error(self) -> None:
        backend = SileroVADBackend(model_path="models/missing-silero.onnx")

        with self.assertRaisesRegex(FileNotFoundError, "Silero VAD model file does not exist"):
            backend.analyze({})

    def test_silero_backend_without_model_path_raises_clear_error(self) -> None:
        backend = SileroVADBackend()

        with self.assertRaisesRegex(RuntimeError, "requires a local --vad-model-path"):
            backend.analyze({})


if __name__ == "__main__":
    unittest.main()
