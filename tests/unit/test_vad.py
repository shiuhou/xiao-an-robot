"""Unit tests for VAD interface placeholders."""

from __future__ import annotations

import sys
import struct
import tempfile
import types
import unittest
from unittest.mock import patch

from base_station.perception.vad import (
    EnergyVADBackend,
    FakeVADBackend,
    FakeVoiceActivityDetector,
    SileroVADBackend,
    SileroVoiceActivityDetector,
    VoiceActivityDetector,
    VoiceActivitySource,
)


class FakeTensor:
    def __init__(self, values: list[float]):
        self.values = list(values)

    def numel(self) -> int:
        return len(self.values)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return FakeTensor(self.values[key])
        return self.values[key]

    def __truediv__(self, value: float):
        return FakeTensor([item / value for item in self.values])

    def reshape(self, frame_count: int, channels: int):
        rows = []
        for index in range(frame_count):
            start = index * channels
            rows.append(self.values[start : start + channels])
        return FakeMatrix(rows)


class FakeMatrix:
    def __init__(self, rows: list[list[float]]):
        self.rows = rows

    def mean(self, dim: int):
        if dim != 1:
            raise ValueError("FakeMatrix only supports mean(dim=1).")
        return FakeTensor([sum(row) / len(row) for row in self.rows])


def fake_torch_module() -> types.ModuleType:
    module = types.ModuleType("torch")
    module.float32 = "float32"
    module.tensor = lambda values, dtype=None: FakeTensor([float(value) for value in values])
    module.empty = lambda size, dtype=None: FakeTensor([])
    return module


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

    def setUp(self) -> None:
        SileroVADBackend._model = None

    def test_silero_backend_missing_package_raises_clear_error(self) -> None:
        backend = SileroVADBackend()

        with patch.dict(sys.modules, {"silero_vad": None, "torch": fake_torch_module()}):
            with self.assertRaisesRegex(ImportError, "requires the silero-vad package"):
                backend.analyze({
                    "pcm_bytes": b"\x00\x00" * 160,
                    "sample_rate": 16000,
                    "sample_width": 2,
                    "channels": 1,
                })

    def test_silero_backend_without_model_path_uses_package_model(self) -> None:
        backend = SileroVADBackend()
        fake_module = types.ModuleType("silero_vad")
        fake_module.load_silero_vad = lambda: "fake-model"
        fake_module.get_speech_timestamps = lambda wav, model, **kwargs: [{"start": 0.25, "end": 0.75}]

        with patch.dict(sys.modules, {"silero_vad": fake_module, "torch": fake_torch_module()}):
            result = backend.analyze({
                "pcm_bytes": b"\x00\x00" * 160,
                "sample_rate": 16000,
                "sample_width": 2,
                "channels": 1,
                "duration_ms": 1000,
            })

        self.assertTrue(result["speech_detected"])
        self.assertEqual(result["backend"], "silero")
        self.assertEqual(result["reason"], "silero")
        self.assertEqual(result["timestamps"], [{"start": 0.25, "end": 0.75}])
        self.assertEqual(result["start_ms"], 250)
        self.assertEqual(result["end_ms"], 750)

    def test_silero_backend_no_timestamps_reports_no_speech(self) -> None:
        backend = SileroVADBackend(threshold=0.5)
        fake_module = types.ModuleType("silero_vad")
        fake_module.load_silero_vad = lambda: "fake-model"
        fake_module.get_speech_timestamps = lambda wav, model, **kwargs: []

        with patch.dict(sys.modules, {"silero_vad": fake_module, "torch": fake_torch_module()}):
            result = backend.analyze({
                "pcm_bytes": b"\x00\x00" * 160,
                "sample_rate": 16000,
                "sample_width": 2,
                "channels": 1,
            })

        self.assertFalse(result["speech_detected"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertIsNone(result["start_ms"])
        self.assertIsNone(result["end_ms"])

    def test_silero_backend_converts_16_bit_pcm_to_float_tensor(self) -> None:
        with patch.dict(sys.modules, {"torch": fake_torch_module()}):
            tensor = SileroVADBackend._pcm_to_float_tensor(
                struct.pack("<hhh", -32768, 0, 32767),
                sample_width=2,
                channels=1,
            )

        self.assertAlmostEqual(float(tensor[0]), -1.0, places=5)
        self.assertAlmostEqual(float(tensor[1]), 0.0, places=5)
        self.assertAlmostEqual(float(tensor[2]), 32767 / 32768.0, places=5)

    def test_silero_backend_converts_stereo_to_mono(self) -> None:
        with patch.dict(sys.modules, {"torch": fake_torch_module()}):
            tensor = SileroVADBackend._pcm_to_float_tensor(
                struct.pack("<hhhh", 32767, -32767, 1000, 3000),
                sample_width=2,
                channels=2,
            )

        self.assertAlmostEqual(float(tensor[0]), 0.0, places=4)
        self.assertAlmostEqual(float(tensor[1]), 2000 / 32768.0, places=5)

    def test_silero_backend_unsupported_sample_width_raises_clear_error(self) -> None:
        backend = SileroVADBackend()

        with self.assertRaisesRegex(RuntimeError, "16-bit PCM WAV only"):
            backend.analyze({
                "pcm_bytes": b"\x00" * 160,
                "sample_rate": 16000,
                "sample_width": 1,
                "channels": 1,
            })

    def test_silero_backend_unsupported_sample_rate_raises_clear_error(self) -> None:
        backend = SileroVADBackend()

        with self.assertRaisesRegex(RuntimeError, "supports 8000 Hz or 16000 Hz"):
            backend.analyze({
                "pcm_bytes": b"\x00\x00" * 160,
                "sample_rate": 44100,
                "sample_width": 2,
                "channels": 1,
            })


if __name__ == "__main__":
    unittest.main()
