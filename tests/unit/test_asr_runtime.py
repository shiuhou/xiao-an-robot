"""Unit tests for standalone ASR runtime helpers."""

from __future__ import annotations

import math
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import wave

from base_station.monitor.asr_runtime import (
    build_asr_event,
    build_audio_file_event,
    build_output,
    create_vad_backend,
    resolve_transcript,
    run_once,
)
from tests.unit.test_vad import fake_torch_module


def write_wav(path: Path, *, sample_rate: int = 16000, seconds: float = 1.0, sine: bool = True) -> None:
    frame_count = int(sample_rate * seconds)
    frames = bytearray()
    for index in range(frame_count):
        value = 0
        if sine:
            value = int(12000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))


class FakeBrain:
    def __init__(self, handled: bool = False, reason: str = "normal", extra_result: dict | None = None) -> None:
        self.events = []
        self.handled = handled
        self.reason = reason
        self.extra_result = extra_result or {}

    async def handle_event(self, event: dict) -> dict:
        self.events.append(event)
        result = {
            "handled": self.handled,
            "reason": self.reason,
            "trigger_result": {
                "reason": self.reason,
            },
        }
        result.update(self.extra_result)
        return result


class ASRRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_pattern_tired_maps_to_tired_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="tired"), "我有点累")

    async def test_pattern_negative_maps_to_negative_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="negative"), "我今天好烦")

    async def test_pattern_normal_maps_to_normal_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="normal"), "帮我查一下天气")

    async def test_pattern_openclaw_maps_to_weather_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="openclaw"), "帮我查一下天气")

    async def test_pattern_greeting_maps_to_greeting_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="greeting"), "你好小安")

    async def test_pattern_summary_maps_to_summary_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="summary"), "生成今天总结")

    async def test_pattern_work_maps_to_work_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="work"), "我刚刚在写项目代码")

    async def test_text_takes_priority_over_pattern(self) -> None:
        text = resolve_transcript(text="我想休息一下", pattern="normal")

        self.assertEqual(text, "我想休息一下")

    async def test_missing_text_and_pattern_uses_normal_pattern(self) -> None:
        self.assertEqual(resolve_transcript(), "帮我查一下天气")

    async def test_unsupported_pattern_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported ASR pattern"):
            resolve_transcript(pattern="unknown")

    async def test_build_asr_event_uses_asr_transcript_type(self) -> None:
        event = build_asr_event("我有点累")

        self.assertEqual(event["type"], "asr.transcript")
        self.assertEqual(event["payload"]["text"], "我有点累")

    async def test_build_asr_event_can_include_audio_vad_asr_metadata(self) -> None:
        event = build_asr_event(
            "我有点累",
            source="audio_file",
            vad={"speech_detected": True},
            asr={"backend": "fake"},
            audio={"sample_rate": 16000},
        )

        self.assertEqual(event["payload"]["source"], "audio_file")
        self.assertEqual(event["payload"]["vad"]["speech_detected"], True)
        self.assertEqual(event["payload"]["asr"]["backend"], "fake")
        self.assertEqual(event["payload"]["audio"]["sample_rate"], 16000)

    async def test_build_output_preserves_openclaw_followup_fields(self) -> None:
        event = build_asr_event("我有点累")
        result = {
            "handled": True,
            "reason": "asr_emotion_triggered",
            "trigger_result": {"reason": "fatigue_keyword"},
            "route": "link_3_companion_fast_path",
            "openclaw_event_type": "companion.request",
            "openclaw_result": {
                "handled": True,
                "reply_text": "收到，我会交给 OpenClaw 处理。",
                "executed_actions": [{"name": "robot.say"}],
                "skipped_actions": [],
            },
            "openclaw_error": "temporary error",
        }

        output = build_output("我有点累", event, result)

        self.assertEqual(output["route"], "link_3_companion_fast_path")
        self.assertEqual(output["openclaw_event_type"], "companion.request")
        self.assertEqual(output["openclaw_result"]["reply_text"], "收到，我会交给 OpenClaw 处理。")
        self.assertEqual(output["openclaw_error"], "temporary error")

    async def test_run_once_uses_fake_brain_without_websocket(self) -> None:
        brain = FakeBrain(handled=True, reason="asr_emotion_triggered")

        output = await run_once(pattern="tired", brain=brain)

        self.assertEqual(output["text"], "我有点累")
        self.assertEqual(output["event_type"], "asr.transcript")
        self.assertTrue(output["handled"])
        self.assertEqual(output["reason"], "asr_emotion_triggered")
        self.assertEqual(brain.events[0]["type"], "asr.transcript")

    async def test_audio_file_fake_vad_and_fake_asr_builds_transcript_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "speech.wav"
            write_wav(audio_path)

            event, prepared = build_audio_file_event(
                audio_path=str(audio_path),
                vad_backend="fake",
                vad_pattern="speech",
                asr_backend="fake",
                fake_transcript="我有点累",
            )

        self.assertIsNotNone(event)
        self.assertEqual(event["type"], "asr.transcript")
        self.assertEqual(event["payload"]["text"], "我有点累")
        self.assertEqual(event["payload"]["source"], "audio_file")
        self.assertEqual(event["payload"]["vad"]["speech_detected"], True)
        self.assertEqual(event["payload"]["asr"]["backend"], "fake")
        self.assertEqual(event["payload"]["audio"]["sample_rate"], 16000)
        self.assertEqual(event["payload"]["audio"]["channels"], 1)
        self.assertEqual(prepared["audio"]["duration_ms"], 1000)

    async def test_audio_file_fake_vad_silence_skips_asr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "silence.wav"
            write_wav(audio_path, sine=False)

            event, output = build_audio_file_event(
                audio_path=str(audio_path),
                vad_backend="fake",
                vad_pattern="silence",
                asr_backend="fake",
                fake_transcript="这句话不应该出现",
            )

        self.assertIsNone(event)
        self.assertEqual(output["event_type"], "asr.no_speech")
        self.assertEqual(output["reason"], "vad_no_speech")
        self.assertFalse(output["vad"]["speech_detected"])
        self.assertNotIn("asr", output)

    async def test_audio_file_empty_asr_returns_empty_transcript_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "speech.wav"
            write_wav(audio_path)

            event, output = build_audio_file_event(
                audio_path=str(audio_path),
                vad_backend="fake",
                vad_pattern="speech",
                asr_backend="fake",
                fake_transcript="   ",
            )

        self.assertIsNone(event)
        self.assertEqual(output["event_type"], "asr.empty_transcript")
        self.assertEqual(output["reason"], "asr_empty_transcript")
        self.assertEqual(output["asr"]["text"], "   ")

    async def test_audio_file_missing_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "Audio file does not exist"):
            build_audio_file_event(audio_path="runtime/manual_samples/missing.wav")

    async def test_run_once_audio_file_no_agent_does_not_create_brain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "speech.wav"
            write_wav(audio_path)
            with patch("base_station.monitor.asr_runtime.XiaoAnBrain") as brain_class:
                output = await run_once(
                    source="audio_file",
                    audio_path=str(audio_path),
                    vad_backend="fake",
                    vad_pattern="speech",
                    asr_backend="fake",
                    fake_transcript="我有点累",
                    no_agent=True,
                )

        brain_class.assert_not_called()
        self.assertEqual(output["event_type"], "asr.transcript")
        self.assertEqual(output["event"]["payload"]["text"], "我有点累")
        self.assertEqual(output["reason"], "no_agent")

    async def test_run_once_audio_file_silence_returns_no_speech(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "silence.wav"
            write_wav(audio_path, sine=False)
            output = await run_once(
                source="audio_file",
                audio_path=str(audio_path),
                vad_backend="fake",
                vad_pattern="silence",
                asr_backend="fake",
                fake_transcript="这句话不应该出现",
                no_agent=True,
            )

        self.assertEqual(output["event_type"], "asr.no_speech")
        self.assertFalse(output["vad"]["speech_detected"])

    async def test_silero_vad_backend_no_longer_requires_model_path(self) -> None:
        backend = create_vad_backend("silero", threshold=0.5)

        self.assertIsNone(backend.model_path)
        self.assertEqual(backend.threshold, 0.5)

    async def test_audio_file_silero_no_speech_skips_asr(self) -> None:
        fake_module = types.ModuleType("silero_vad")
        fake_module.load_silero_vad = lambda: "fake-model"
        fake_module.get_speech_timestamps = lambda wav, model, **kwargs: []

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "silence.wav"
            write_wav(audio_path, sine=False)
            with patch.dict(sys.modules, {"silero_vad": fake_module, "torch": fake_torch_module()}):
                event, output = build_audio_file_event(
                    audio_path=str(audio_path),
                    vad_backend="silero",
                    asr_backend="fake",
                    fake_transcript="这句话不应该出现",
                )

        self.assertIsNone(event)
        self.assertEqual(output["event_type"], "asr.no_speech")
        self.assertEqual(output["vad"]["backend"], "silero")
        self.assertFalse(output["vad"]["speech_detected"])
        self.assertNotIn("asr", output)

    async def test_run_once_openclaw_pattern_exposes_openclaw_route(self) -> None:
        brain = FakeBrain(
            handled=True,
            reason="openclaw_decision",
            extra_result={
                "route": "link_1_openclaw",
                "reply_text": "收到，我会交给 OpenClaw 处理。",
                "executed_actions": [
                    {
                        "name": "robot.say",
                        "source": "reply_text",
                        "arguments": {"text": "收到，我会交给 OpenClaw 处理。"},
                    }
                ],
                "skipped_actions": [],
            },
        )

        output = await run_once(pattern="openclaw", brain=brain)

        self.assertEqual(output["text"], "帮我查一下天气")
        self.assertTrue(output["handled"])
        self.assertEqual(output["route"], "link_1_openclaw")
        self.assertEqual(output["reason"], "openclaw_decision")
        self.assertEqual(output["reply_text"], "收到，我会交给 OpenClaw 处理。")
        self.assertEqual(output["executed_actions"][0]["name"], "robot.say")
        self.assertEqual(output["skipped_actions"], [])


if __name__ == "__main__":
    unittest.main()
