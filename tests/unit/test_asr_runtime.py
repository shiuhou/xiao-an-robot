"""Unit tests for standalone ASR runtime helpers."""

from __future__ import annotations

import unittest

from base_station.monitor.asr_runtime import build_asr_event, resolve_transcript, run_once


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

    async def test_run_once_uses_fake_brain_without_websocket(self) -> None:
        brain = FakeBrain(handled=True, reason="asr_emotion_triggered")

        output = await run_once(pattern="tired", brain=brain)

        self.assertEqual(output["text"], "我有点累")
        self.assertEqual(output["event_type"], "asr.transcript")
        self.assertTrue(output["handled"])
        self.assertEqual(output["reason"], "asr_emotion_triggered")
        self.assertEqual(brain.events[0]["type"], "asr.transcript")

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
