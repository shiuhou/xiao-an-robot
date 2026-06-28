"""Unit tests for ASR interface placeholders."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from base_station.perception.asr import (
    ASRTranscriptSource,
    FakeASRBackend,
    FakeASRTranscriptSource,
    SenseVoiceASRBackend,
    SenseVoiceSmallASRTranscriptSource,
    StreamingASR,
)


class ASRTranscriptSourceTest(unittest.TestCase):
    def test_fake_asr_returns_transcripts_in_order(self) -> None:
        source = FakeASRTranscriptSource(["hello", "world"])

        self.assertEqual(source.read_transcript(), "hello")
        self.assertEqual(source.read_transcript(), "world")

    def test_fake_asr_returns_none_after_exhausted(self) -> None:
        source = FakeASRTranscriptSource(["hello"])

        self.assertEqual(source.read_transcript(), "hello")
        self.assertIsNone(source.read_transcript())

    def test_fake_asr_can_return_none_items(self) -> None:
        source = FakeASRTranscriptSource(["hello", None, "again"])

        self.assertEqual(source.read_transcript(), "hello")
        self.assertIsNone(source.read_transcript())
        self.assertEqual(source.read_transcript(), "again")

    def test_base_asr_source_raises_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError):
            ASRTranscriptSource().read_transcript()

    def test_sensevoice_placeholder_saves_configuration(self) -> None:
        source = SenseVoiceSmallASRTranscriptSource(model_dir="models/sensevoice", device="npu")

        self.assertEqual(source.model_dir, "models/sensevoice")
        self.assertEqual(source.device, "npu")

    def test_sensevoice_read_transcript_raises_not_implemented(self) -> None:
        source = SenseVoiceSmallASRTranscriptSource(model_dir="models/sensevoice")

        with self.assertRaisesRegex(NotImplementedError, "SenseVoice-Small ASR is not implemented yet"):
            source.read_transcript()

    def test_streaming_asr_keeps_model_dir_and_feed_audio_raises(self) -> None:
        source = StreamingASR(model_dir="models/sensevoice", device="cpu")

        self.assertEqual(source.model_dir, "models/sensevoice")
        with self.assertRaises(NotImplementedError):
            source.feed_audio(b"pcm")

    def test_streaming_asr_reset_does_not_raise(self) -> None:
        source = StreamingASR(model_dir="models/sensevoice")

        source.reset()

    def test_fake_asr_backend_uses_explicit_transcript(self) -> None:
        result = FakeASRBackend(transcript="我有点累").transcribe({"duration_ms": 1234})

        self.assertEqual(result["text"], "我有点累")
        self.assertEqual(result["backend"], "fake")
        self.assertEqual(result["duration_ms"], 1234)

    def test_fake_asr_backend_uses_pattern(self) -> None:
        result = FakeASRBackend(pattern="greeting").transcribe({"duration_ms": 1000})

        self.assertEqual(result["text"], "你好小安")

    def test_sensevoice_backend_without_model_path_raises_clear_error(self) -> None:
        backend = SenseVoiceASRBackend()

        with self.assertRaisesRegex(RuntimeError, "requires a local --asr-model-path"):
            backend.transcribe({})

    def test_sensevoice_backend_missing_model_raises_clear_error(self) -> None:
        backend = SenseVoiceASRBackend(model_dir="models/missing-sensevoice")

        with self.assertRaisesRegex(FileNotFoundError, "SenseVoice ASR model directory does not exist"):
            backend.transcribe({})

    def test_sensevoice_backend_empty_model_dir_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = SenseVoiceASRBackend(model_dir=temp_dir)

            with self.assertRaisesRegex(RuntimeError, "model directory is empty"):
                backend.transcribe({})

    def test_sensevoice_backend_missing_funasr_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "config.json").write_text("{}", encoding="utf-8")
            backend = SenseVoiceASRBackend(model_dir=temp_dir)

            with patch.dict(sys.modules, {"funasr": None}):
                with self.assertRaisesRegex(ImportError, "requires funasr installed"):
                    backend.transcribe({"audio_path": "sample.wav"})

    def test_sensevoice_backend_parses_list_dict_result(self) -> None:
        with fake_funasr_module([{"text": "<|zh|><|NEUTRAL|> 我有点累 ", "score": 0.8}]) as calls:
            backend = SenseVoiceASRBackend(model_dir=populated_temp_model_dir(), device="cpu")

            result = backend.transcribe({"audio_path": "sample.wav", "duration_ms": 1000})

        self.assertEqual(result["text"], "我有点累")
        self.assertEqual(result["language"], "zh")
        self.assertEqual(result["confidence"], 0.8)
        self.assertEqual(result["backend"], "sensevoice")
        self.assertEqual(calls["init"], 1)
        self.assertEqual(calls["generate"], 1)

    def test_sensevoice_backend_parses_dict_result(self) -> None:
        with fake_funasr_module({"text": "你好小安", "language": "zh"}) as _calls:
            backend = SenseVoiceASRBackend(model_dir=populated_temp_model_dir())

            result = backend.transcribe({"audio_path": "sample.wav"})

        self.assertEqual(result["text"], "你好小安")
        self.assertEqual(result["language"], "zh")

    def test_sensevoice_backend_parses_string_result(self) -> None:
        with fake_funasr_module("<|zh|>帮我查一下天气") as _calls:
            backend = SenseVoiceASRBackend(model_dir=populated_temp_model_dir())

            result = backend.transcribe({"audio_path": "sample.wav"})

        self.assertEqual(result["text"], "帮我查一下天气")
        self.assertEqual(result["language"], "zh")

    def test_sensevoice_backend_keeps_empty_text_empty(self) -> None:
        with fake_funasr_module([{"text": "   "}]) as _calls:
            backend = SenseVoiceASRBackend(model_dir=populated_temp_model_dir())

            result = backend.transcribe({"audio_path": "sample.wav"})

        self.assertEqual(result["text"], "")

    def test_sensevoice_backend_lazy_loads_model_once(self) -> None:
        with fake_funasr_module({"text": "你好"}) as calls:
            backend = SenseVoiceASRBackend(model_dir=populated_temp_model_dir())

            backend.transcribe({"audio_path": "one.wav"})
            backend.transcribe({"audio_path": "two.wav"})

        self.assertEqual(calls["init"], 1)
        self.assertEqual(calls["generate"], 2)


def populated_temp_model_dir() -> str:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name)
    path.joinpath("config.json").write_text("{}", encoding="utf-8")
    _TEMP_DIRS.append(temp_dir)
    return str(path)


_TEMP_DIRS: list[tempfile.TemporaryDirectory] = []


class fake_funasr_module:
    def __init__(self, generate_result):
        self.generate_result = generate_result
        self.calls = {"init": 0, "generate": 0}
        self.previous = sys.modules.get("funasr", _MISSING)

    def __enter__(self):
        calls = self.calls
        generate_result = self.generate_result

        class FakeAutoModel:
            def __init__(self, **_kwargs):
                calls["init"] += 1

            def generate(self, **_kwargs):
                calls["generate"] += 1
                return generate_result

        sys.modules["funasr"] = types.SimpleNamespace(AutoModel=FakeAutoModel)
        return self.calls

    def __exit__(self, _exc_type, _exc, _tb):
        if self.previous is _MISSING:
            sys.modules.pop("funasr", None)
        else:
            sys.modules["funasr"] = self.previous


_MISSING = object()


if __name__ == "__main__":
    unittest.main()
