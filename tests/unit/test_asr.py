"""Unit tests for ASR interface placeholders."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
