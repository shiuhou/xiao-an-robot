"""Unit tests for VAD interface placeholders."""

from __future__ import annotations

import unittest

from base_station.perception.vad import (
    FakeVoiceActivityDetector,
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


if __name__ == "__main__":
    unittest.main()
