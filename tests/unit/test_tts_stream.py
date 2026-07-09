"""Unit tests for base-station TTS PCM preparation."""

from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import wave

from base_station.ws_server.tts_stream import (
    TTS_COMMAND_ENV,
    TTS_RATE_ENV,
    TTS_VOICE_ENV,
    TTS_TARGET_PEAK_ENV,
    default_edge_tts_command_template,
    default_edge_tts_script_path,
    windows_sapi_script,
    external_tts_backend_configured,
    limit_pcm_peak_s16le,
    normalize_pcm_peak_s16le,
    synthesize_tts_pcm_stream,
    tts_target_peak_from_env,
    tts_command_template_from_env,
)


def _write_test_wav(path: Path, pcm: bytes | None = None) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm if pcm is not None else struct.pack("<hhhh", -1000, 0, 500, 1000))


class TtsStreamTest(unittest.TestCase):
    def test_limit_pcm_peak_scales_full_range_speech_to_speaker_safe_level(self) -> None:
        pcm = struct.pack("<hhhh", -32768, -16000, 1000, 32767)

        limited = limit_pcm_peak_s16le(pcm, target_peak=2800)
        samples = struct.unpack("<hhhh", limited)

        self.assertLessEqual(max(abs(sample) for sample in samples), 2800)
        self.assertGreater(abs(samples[3]), 2500)
        self.assertEqual(len(limited), len(pcm))

    def test_normalize_pcm_peak_boosts_quiet_pcm(self) -> None:
        pcm = struct.pack("<hhh", -1200, 0, 1500)

        normalized = normalize_pcm_peak_s16le(pcm, target_peak=2800)
        samples = struct.unpack("<hhh", normalized)

        self.assertLessEqual(max(abs(sample) for sample in samples), 2800)
        self.assertGreater(max(abs(sample) for sample in samples), 2600)

    def test_default_tts_peak_limit_matches_buffered_speaker_baseline(self) -> None:
        pcm = struct.pack("<hh", -32768, 32767)

        limited = limit_pcm_peak_s16le(pcm)
        samples = struct.unpack("<hh", limited)

        self.assertLessEqual(max(abs(sample) for sample in samples), 500)
        self.assertGreater(max(abs(sample) for sample in samples), 450)

    def test_tts_target_peak_can_be_lowered_for_quiet_hardware_smoke(self) -> None:
        with mock.patch.dict("os.environ", {TTS_TARGET_PEAK_ENV: "800"}, clear=False):
            self.assertEqual(tts_target_peak_from_env(), 800)

        pcm = struct.pack("<hhh", -4000, 0, 2000)
        quiet = normalize_pcm_peak_s16le(pcm, target_peak=800)
        samples = struct.unpack("<hhh", quiet)

        self.assertLessEqual(max(abs(sample) for sample in samples), 800)
        self.assertGreater(max(abs(sample) for sample in samples), 700)

    def test_tts_target_peak_invalid_env_uses_default(self) -> None:
        with mock.patch.dict("os.environ", {TTS_TARGET_PEAK_ENV: "not-a-number"}, clear=False):
            self.assertEqual(tts_target_peak_from_env(), 500)

    def test_windows_sapi_script_prefers_mandarin_voice_before_zh_hk(self) -> None:
        script = windows_sapi_script()

        self.assertIn(TTS_VOICE_ENV, script)
        self.assertIn("'zh-CN'", script)
        self.assertIn("'zh-TW'", script)
        self.assertIn("'zh-HK'", script)
        self.assertLess(script.index("'zh-CN'"), script.index("'zh-TW'"))
        self.assertLess(script.index("'zh-TW'"), script.index("'zh-HK'"))

    def test_windows_sapi_script_supports_speech_rate_env(self) -> None:
        script = windows_sapi_script()

        self.assertIn(TTS_RATE_ENV, script)
        self.assertIn("$synth.Rate", script)

    def test_default_external_tts_command_targets_runtime_edge_tts_script(self) -> None:
        command = default_edge_tts_command_template()

        self.assertTrue(str(default_edge_tts_script_path()).endswith("runtime/tts_probe/edge_tts_to_wav.py"))
        self.assertIn("edge_tts_to_wav.py", command)
        self.assertIn("{text_file}", command)
        self.assertIn("{wav_file}", command)

    def test_external_tts_command_env_overrides_default_edge_script(self) -> None:
        with mock.patch.dict("os.environ", {TTS_COMMAND_ENV: "custom_tts {text_file} {wav_file}"}, clear=False):
            self.assertEqual(tts_command_template_from_env(), "custom_tts {text_file} {wav_file}")
            self.assertTrue(external_tts_backend_configured())

    def test_synthesize_tts_reuses_cache_without_external_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calls: list[Path] = []

            def write_wav(_text_path: Path, wav_path: Path) -> None:
                calls.append(wav_path)
                _write_test_wav(wav_path)

            with (
                mock.patch.dict("os.environ", {TTS_COMMAND_ENV: "fake_tts {text_file} {wav_file}"}, clear=False),
                mock.patch("base_station.ws_server.tts_stream._run_external_tts_command", side_effect=write_wav),
            ):
                first = synthesize_tts_pcm_stream("缓存测试", runtime_dir=temp_dir)
                second = synthesize_tts_pcm_stream("缓存测试", runtime_dir=temp_dir)

        self.assertEqual(len(calls), 1)
        self.assertEqual(first.pcm, second.pcm)
        self.assertEqual(first.sample_rate, 16000)
        self.assertEqual(second.channels, 1)

    def test_synthesize_tts_falls_back_to_legacy_wav_when_external_command_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            tts_dir = runtime / "tts"
            tts_dir.mkdir()
            text_path = tts_dir / "tts-old-1.txt"
            wav_path = tts_dir / "tts-old-1.wav"
            text_path.write_text("网络失败兜底", encoding="utf-8")
            _write_test_wav(wav_path)

            with (
                mock.patch.dict("os.environ", {TTS_COMMAND_ENV: "fake_tts {text_file} {wav_file}"}, clear=False),
                mock.patch(
                    "base_station.ws_server.tts_stream._run_external_tts_command",
                    side_effect=RuntimeError("Temporary failure in name resolution"),
                ),
            ):
                stream = synthesize_tts_pcm_stream("网络失败兜底", runtime_dir=runtime)

            cached_files = list((runtime / "tts_cache").glob("*.wav"))

        self.assertEqual(stream.sample_rate, 16000)
        self.assertEqual(stream.channels, 1)
        self.assertGreater(len(stream.pcm), 0)
        self.assertEqual(len(cached_files), 1)


if __name__ == "__main__":
    unittest.main()
