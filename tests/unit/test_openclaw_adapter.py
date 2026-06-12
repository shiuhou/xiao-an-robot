"""Unit tests for OpenClaw adapter protocol objects."""

from __future__ import annotations

import unittest

from agent.core.openclaw_adapter import (
    FakeOpenClawAdapter,
    OpenClawDecision,
    OpenClawEvent,
    OpenClawToolCall,
)


class OpenClawAdapterTest(unittest.TestCase):
    def test_openclaw_event_defaults_are_correct(self) -> None:
        event = OpenClawEvent(type="asr.transcript")

        self.assertEqual(event.type, "asr.transcript")
        self.assertIsNone(event.text)
        self.assertEqual(event.source, "unknown")
        self.assertEqual(event.session_id, "default")
        self.assertEqual(event.context, {})

    def test_openclaw_tool_call_default_arguments_is_empty_dict(self) -> None:
        tool_call = OpenClawToolCall(name="robot.say")

        self.assertEqual(tool_call.name, "robot.say")
        self.assertEqual(tool_call.arguments, {})

    def test_openclaw_decision_default_tool_calls_is_empty_list(self) -> None:
        decision = OpenClawDecision(handled=True)

        self.assertTrue(decision.handled)
        self.assertEqual(decision.reply_text, "")
        self.assertEqual(decision.tool_calls, [])
        self.assertIsNone(decision.raw)

    def test_fake_openclaw_adapter_default_decision_is_usable(self) -> None:
        adapter = FakeOpenClawAdapter()
        decision = adapter.handle_event(OpenClawEvent(type="test.event"))

        self.assertTrue(decision.handled)
        self.assertEqual(decision.reply_text, "收到，我会交给 OpenClaw 处理。")
        self.assertEqual(decision.tool_calls, [])

    def test_fake_openclaw_adapter_records_event(self) -> None:
        adapter = FakeOpenClawAdapter()
        event = OpenClawEvent(type="asr.transcript", text="我有点累", source="asr")

        adapter.handle_event(event)

        self.assertEqual(adapter.events, [event])

    def test_fake_openclaw_adapter_supports_custom_decision(self) -> None:
        decision = OpenClawDecision(
            handled=True,
            reply_text="测试回复",
            tool_calls=[
                OpenClawToolCall(
                    name="robot.say",
                    arguments={"text": "你好"},
                ),
            ],
        )
        adapter = FakeOpenClawAdapter(decision=decision)

        result = adapter.handle_event(OpenClawEvent(type="test.event"))

        self.assertIs(result, decision)
        self.assertEqual(result.reply_text, "测试回复")
        self.assertEqual(result.tool_calls[0].name, "robot.say")
        self.assertEqual(result.tool_calls[0].arguments, {"text": "你好"})


if __name__ == "__main__":
    unittest.main()
