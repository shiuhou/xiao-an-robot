"""Unit tests for the assistant capture demo."""

from __future__ import annotations

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import tempfile
import unittest
from pathlib import Path

from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall
from tools.demo.demo_assistant_capture import (
    assistant_capture_tool_manifest,
    build_openclaw_context,
    capture_from_decision,
    feedback_plan,
    infer_capture_hint,
    parse_args,
    run_demo,
    validate_capture_decision,
)


class AssistantCaptureHelpersTest(unittest.TestCase):
    def test_context_marks_openclaw_as_source_of_truth(self) -> None:
        context = build_openclaw_context(
            transcript="帮我记一下，下星期有会议",
            transcript_source="mock",
        )

        self.assertEqual(context["schema_version"], "xiaoan.assistant_capture_context.v1")
        self.assertEqual(context["source"], "base_station_mic")
        self.assertEqual(context["demo_intent"], "assistant_capture")
        self.assertEqual(
            context["capture_policy"]["source_of_truth"],
            "openclaw_xiaoan_runtime",
        )
        self.assertFalse(context["capture_policy"]["local_sqlite_is_product_source"])
        self.assertIn("meeting", context["capture_expectation"]["allowed_kinds"])
        self.assertEqual(context["capture_hint"]["kind_hint"], "meeting")

    def test_infer_capture_hint_covers_idea_and_reminder(self) -> None:
        idea = infer_capture_hint("这个想法先存一下")
        reminder = infer_capture_hint("待会提醒我喝水")

        self.assertEqual(idea["kind_hint"], "idea")
        self.assertEqual(reminder["kind_hint"], "reminder")
        self.assertTrue(idea["likely_capture"])
        self.assertTrue(reminder["likely_capture"])

    def test_tool_manifest_excludes_local_memory_compat_tools(self) -> None:
        names = {item["name"] for item in assistant_capture_tool_manifest()}

        self.assertEqual(names, {"xiaoan.robot.expression", "xiaoan.robot.say"})
        self.assertNotIn("note.add", names)
        self.assertNotIn("reminder.add", names)
        self.assertNotIn("task.add", names)

    def test_validate_accepts_openclaw_capture_result(self) -> None:
        decision = OpenClawDecision(
            handled=True,
            reply_text="已记录。",
            raw={
                "handled": True,
                "reply_text": "已记录。",
                "capture": {
                    "ok": True,
                    "status": "captured",
                    "kind": "idea",
                    "title": "做一个主动记事的小安",
                    "source_of_truth": "openclaw_xiaoan_runtime",
                },
            },
        )

        validation = validate_capture_decision(decision)

        self.assertTrue(validation["ok"])
        self.assertEqual(validation["capture"]["status"], "captured")

    def test_validate_rejects_reply_text_only(self) -> None:
        decision = OpenClawDecision(handled=True, reply_text="已记录。")

        validation = validate_capture_decision(decision)

        self.assertFalse(validation["ok"])
        self.assertIn("decision.raw.capture is required", validation["errors"][0])

    def test_validate_rejects_local_compat_tool_as_product_source(self) -> None:
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(name="reminder.add", arguments={"message": "喝水"}),
            ],
            raw={
                "handled": True,
                "capture": {
                    "status": "captured",
                    "kind": "reminder",
                    "title": "喝水",
                    "source_of_truth": "openclaw_xiaoan_runtime",
                },
            },
        )

        validation = validate_capture_decision(decision)

        self.assertFalse(validation["ok"])
        self.assertIn("local compatibility tool", validation["errors"][0])

    def test_capture_from_decision_supports_nested_payload(self) -> None:
        decision = OpenClawDecision(
            handled=True,
            raw={
                "payload": {
                    "result": {
                        "capture": {
                            "status": "needs_clarification",
                            "kind": "meeting",
                            "source_of_truth": "openclaw_xiaoan_runtime",
                        }
                    }
                }
            },
        )

        self.assertEqual(capture_from_decision(decision)["kind"], "meeting")

    def test_feedback_plan_uses_reliable_local_sound_for_success(self) -> None:
        success = feedback_plan("captured", "已记录")
        clarification = feedback_plan("needs_clarification", "哪一天几点？")

        self.assertEqual(success["expression"], "happy")
        self.assertEqual(success["local_sound"], "success_ding")
        self.assertEqual(clarification["expression"], "thinking")
        self.assertIsNone(clarification["local_sound"])

    def test_decision_only_requires_openclaw_route(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(["--mock-text", "待会提醒我喝水", "--openclaw-decision-only"])


class AssistantCaptureRunDemoTest(unittest.TestCase):
    def test_mock_context_only_writes_ignored_state_without_local_sqlite_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            args = parse_args([
                "--mock-text",
                "这个想法先存一下：做一个主动记事的小安",
                "--state-path",
                str(root / "assistant_capture_result.json"),
                "--text-path",
                str(root / "assistant_capture_transcript.txt"),
                "--context-path",
                str(root / "assistant_capture_context.json"),
                "--log-path",
                str(root / "assistant_capture.log.jsonl"),
            ])

            with redirect_stdout(io.StringIO()):
                exit_code = asyncio.run(run_demo(args))
            state = json.loads((root / "assistant_capture_result.json").read_text(encoding="utf-8"))
            context = json.loads((root / "assistant_capture_context.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(state["status"], "ignored")
        self.assertEqual(state["source_of_truth"], "openclaw_xiaoan_runtime")
        self.assertFalse(state["local_sqlite_is_product_source"])
        self.assertEqual(context["capture_hint"]["kind_hint"], "idea")

    def test_empty_mock_text_fails_without_capture_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context_path = root / "assistant_capture_context.json"
            args = parse_args([
                "--mock-text",
                "   ",
                "--state-path",
                str(root / "assistant_capture_result.json"),
                "--text-path",
                str(root / "assistant_capture_transcript.txt"),
                "--context-path",
                str(context_path),
                "--log-path",
                str(root / "assistant_capture.log.jsonl"),
            ])

            with redirect_stderr(io.StringIO()):
                exit_code = asyncio.run(run_demo(args))
            state = json.loads((root / "assistant_capture_result.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(state["status"], "error")
        self.assertIn("--mock-text must not be empty", state["error"])
        self.assertFalse(context_path.exists())


if __name__ == "__main__":
    unittest.main()
