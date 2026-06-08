"""Unit tests for standalone ASR runtime helpers."""

from __future__ import annotations

import unittest

from base_station.monitor.asr_runtime import build_asr_event, resolve_transcript, run_once


class FakeBrain:
    def __init__(self, handled: bool = False, reason: str = "normal") -> None:
        self.events = []
        self.handled = handled
        self.reason = reason

    async def handle_event(self, event: dict) -> dict:
        self.events.append(event)
        return {
            "handled": self.handled,
            "reason": self.reason,
            "trigger_result": {
                "reason": self.reason,
            },
        }


class ASRRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_pattern_tired_maps_to_tired_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="tired"), "我有点累")

    async def test_pattern_negative_maps_to_negative_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="negative"), "我今天好烦")

    async def test_pattern_normal_maps_to_normal_text(self) -> None:
        self.assertEqual(resolve_transcript(pattern="normal"), "帮我查一下天气")

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

    async def test_run_once_uses_fake_brain_without_websocket(self) -> None:
        brain = FakeBrain(handled=True, reason="asr_emotion_triggered")

        output = await run_once(pattern="tired", brain=brain)

        self.assertEqual(output["text"], "我有点累")
        self.assertEqual(output["event_type"], "asr.transcript")
        self.assertTrue(output["handled"])
        self.assertEqual(output["reason"], "asr_emotion_triggered")
        self.assertEqual(brain.events[0]["type"], "asr.transcript")


if __name__ == "__main__":
    unittest.main()
