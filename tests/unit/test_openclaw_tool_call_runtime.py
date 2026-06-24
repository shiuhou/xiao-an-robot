"""Unit tests for fake OpenClaw tool_call runtime flow."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.action_executor import ActionExecutor
from agent.core.brain import XiaoAnBrain
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision, OpenClawToolCall
from tools import test_openclaw_tool_calls as manual_tool_calls


class FakeRobotMotionSkill:
    def __init__(self) -> None:
        self.calls = []

    async def say(self, text: str) -> dict:
        self.calls.append(("say", text))
        return {"ok": True, "text": text}

    async def show_expression(self, expression: str) -> dict:
        self.calls.append(("expression", expression))
        return {"ok": True, "expression": expression}

    async def move_out_of_dock(self) -> dict:
        self.calls.append(("move_out_of_dock", None))
        return {"ok": True}

    async def return_to_dock(self) -> dict:
        self.calls.append(("return_to_dock", None))
        return {"ok": True}


class FakeMemory:
    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        timestamp: int | None = None,
    ) -> int:
        return 1

    def get_recent_summary(self, seconds: int = 300, now_ms: int | None = None) -> dict:
        return {
            "count": 0,
            "avg_fatigue_score": 0.0,
            "max_confidence": 0.0,
            "top_emotion": None,
            "emotions_count": {},
        }

    def close(self) -> None:
        pass


class OpenClawToolCallRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def build_brain(self, decision: OpenClawDecision, fake_robot: FakeRobotMotionSkill) -> XiaoAnBrain:
        return XiaoAnBrain(
            gateway=None,
            memory=FakeMemory(),
            openclaw_adapter=FakeOpenClawAdapter(decision=decision),
            action_executor=ActionExecutor(robot_motion_skill=fake_robot),
        )

    async def test_frontend_message_executes_note_add_tool_call(self) -> None:
        fake_robot = FakeRobotMotionSkill()
        brain = self.build_brain(
            OpenClawDecision(
                handled=True,
                reply_text="我已经帮你处理了。",
                tool_calls=[
                    OpenClawToolCall(
                        name="note.add",
                        arguments={"content": "帮我记一下明天下午交报告", "tags": ["manual-test"]},
                    ),
                ],
            ),
            fake_robot,
        )

        result = await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "帮我记一下明天下午交报告", "session_id": "test-session"},
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["route"], "frontend_openclaw")
        self.assertEqual(fake_robot.calls, [("say", "我已经帮你处理了。")])
        note_action = next(action for action in result["executed_actions"] if action["name"] == "note.add")
        self.assertTrue(note_action["result"]["ok"])
        self.assertEqual(note_action["result"]["result"]["content"], "帮我记一下明天下午交报告")

    async def test_asr_transcript_executes_work_context_record_tool_call(self) -> None:
        fake_robot = FakeRobotMotionSkill()
        brain = self.build_brain(
            OpenClawDecision(
                handled=True,
                reply_text="我已经帮你处理了。",
                tool_calls=[
                    OpenClawToolCall(
                        name="work_context.record",
                        arguments={"content": "帮我记录当前工作", "source": "manual-test"},
                    ),
                ],
            ),
            fake_robot,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "帮我记录当前工作", "session_id": "test-session"},
        })

        self.assertEqual(result["route"], "link_1_openclaw")
        self.assertEqual(fake_robot.calls, [("say", "我已经帮你处理了。")])
        work_action = next(action for action in result["executed_actions"] if action["name"] == "work_context.record")
        self.assertTrue(work_action["result"]["ok"])
        self.assertEqual(work_action["result"]["result"]["source"], "manual-test")

    async def test_summary_daily_tool_call_executes_placeholder(self) -> None:
        fake_robot = FakeRobotMotionSkill()
        brain = self.build_brain(
            OpenClawDecision(
                handled=True,
                reply_text="我已经帮你处理了。",
                tool_calls=[
                    OpenClawToolCall(
                        name="summary.daily",
                        arguments={"date": "today"},
                    ),
                ],
            ),
            fake_robot,
        )

        result = await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "生成今天总结", "session_id": "test-session"},
        })

        summary_action = next(action for action in result["executed_actions"] if action["name"] == "summary.daily")
        self.assertEqual(summary_action["result"]["result"]["status"], "placeholder")
        self.assertEqual(fake_robot.calls, [("say", "我已经帮你处理了。")])

    async def test_manual_script_without_record_memory_keeps_output_without_snapshot(self) -> None:
        class FakeBrain:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

            async def handle_event(self, event: dict) -> dict:
                return {"handled": True, "route": "fake"}

            def close(self) -> None:
                pass

        original_brain = manual_tool_calls.XiaoAnBrain
        manual_tool_calls.XiaoAnBrain = FakeBrain
        try:
            args = manual_tool_calls.parse_args(["--tool", "note.add", "--text", "hello"])
            output = await manual_tool_calls.run(args)
        finally:
            manual_tool_calls.XiaoAnBrain = original_brain

        self.assertEqual(output["tool"], "note.add")
        self.assertEqual(output["result"], {"handled": True, "route": "fake"})
        self.assertNotIn("memory_snapshot", output)

    async def test_manual_script_record_memory_note_add_outputs_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "note.add",
                "--text",
                "remember this",
            ])

            output = await manual_tool_calls.run(args)

        snapshot = output["memory_snapshot"]
        self.assertEqual(snapshot["db_path"], str(db_path.resolve()))
        self.assertTrue(any(row["tool_name"] == "note.add" for row in snapshot["recent_tool_runs"]))
        self.assertTrue(any(row["content"] == "remember this" for row in snapshot["recent_notes"]))

    async def test_manual_script_unknown_tool_records_failed_tool_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual_unknown.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "unknown.tool",
                "--text",
                "manual unknown test",
            ])

            self.assertEqual(args.tool, "unknown.tool")
            output = await manual_tool_calls.run(args)

            skipped_actions = output["result"]["skipped_actions"]
            self.assertTrue(any(
                action["name"] == "unknown.tool"
                and action["reason"] == "unknown_tool"
                for action in skipped_actions
            ))

            snapshot = output["memory_snapshot"]
            unknown_runs = [
                row
                for row in snapshot["recent_tool_runs"]
                if row["tool_name"] == "unknown.tool"
            ]
            self.assertEqual(len(unknown_runs), 1)
            self.assertEqual(unknown_runs[0]["status"], "failed")
            self.assertEqual(unknown_runs[0]["error"], "unknown_tool")

            unknown_events = [
                event
                for event in snapshot["recent_events"]
                if event["event_type"] == "tool.run"
                and event["payload"].get("tool_name") == "unknown.tool"
            ]
            self.assertEqual(len(unknown_events), 1)
            self.assertEqual(unknown_events[0]["payload"]["error"], "unknown_tool")

    async def test_manual_script_record_memory_work_context_records_work_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "work_context.record",
                "--text",
                "record current work",
            ])

            output = await manual_tool_calls.run(args)

            snapshot = output["memory_snapshot"]
            self.assertEqual(snapshot["recent_notes"], [])
            self.assertTrue(any(
                row["window_title"] == "record current work"
                for row in snapshot["recent_work_activities"]
            ))

    async def test_manual_script_record_memory_summary_daily_outputs_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "summary.daily",
                "--text",
                "summary today",
            ])

            output = await manual_tool_calls.run(args)

        snapshot = output["memory_snapshot"]
        self.assertTrue(any(row["summary_type"] == "daily" for row in snapshot["recent_summaries"]))
        self.assertTrue(any("今日概览" in row["content"] for row in snapshot["recent_summaries"]))

    async def test_manual_script_fresh_db_clears_previous_test_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            first_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "note.add",
                "--text",
                "old note",
            ])
            await manual_tool_calls.run(first_args)

            second_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--fresh-db",
                "--tool",
                "note.add",
                "--text",
                "new note",
            ])
            output = await manual_tool_calls.run(second_args)

        notes = output["memory_snapshot"]["recent_notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["content"], "new note")

    async def test_manual_script_record_memory_reminder_add_outputs_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "reminder.add",
                "--text",
                "wake me",
                "--delay-seconds",
                "60",
            ])

            output = await manual_tool_calls.run(args)

        reminders = output["memory_snapshot"]["recent_reminders"]
        self.assertEqual(reminders[0]["message"], "wake me")
        self.assertEqual(reminders[0]["status"], "pending")

    async def test_manual_script_record_memory_reminder_query_returns_reminders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            add_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "reminder.add",
                "--text",
                "wake me",
            ])
            await manual_tool_calls.run(add_args)

            query_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "reminder.query",
            ])
            output = await manual_tool_calls.run(query_args)

        query_action = next(action for action in output["result"]["executed_actions"] if action["name"] == "reminder.query")
        self.assertEqual(query_action["result"]["count"], 1)
        self.assertEqual(query_action["result"]["reminders"][0]["message"], "wake me")

    async def test_manual_script_record_memory_reminder_cancel_cancels_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            add_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "reminder.add",
                "--text",
                "wake me",
            ])
            await manual_tool_calls.run(add_args)

            cancel_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "reminder.cancel",
                "--text",
                "wake",
            ])
            output = await manual_tool_calls.run(cancel_args)

        reminders = output["memory_snapshot"]["recent_reminders"]
        self.assertEqual(reminders[0]["message"], "wake me")
        self.assertEqual(reminders[0]["status"], "cancelled")

    def test_manual_script_reminder_cancel_accepts_reminder_id(self) -> None:
        args = manual_tool_calls.parse_args([
            "--tool",
            "reminder.cancel",
            "--text",
            "ignored",
            "--reminder-id",
            "42",
        ])

        call = manual_tool_calls.build_tool_call(
            args.tool,
            args.text,
            reminder_id=args.reminder_id,
        )

        self.assertEqual(call.arguments["reminder_id"], 42)
        self.assertEqual(call.arguments["message_contains"], "ignored")

    def test_manual_script_builds_project_query_tool_arguments(self) -> None:
        note_call = manual_tool_calls.build_tool_call(
            "note.search",
            "report",
            limit=3,
        )
        work_call = manual_tool_calls.build_tool_call(
            "work_context.query",
            "Step 27",
            limit=4,
        )
        summary_call = manual_tool_calls.build_tool_call(
            "summary.query",
            manual_tool_calls.DEFAULT_TEXT,
            date="2026-06-22",
            limit=2,
            summary_type="daily",
        )

        self.assertEqual(note_call.arguments, {"keyword": "report", "limit": 3})
        self.assertEqual(work_call.arguments, {"keyword": "Step 27", "limit": 4})
        self.assertEqual(summary_call.arguments, {
            "date": "2026-06-22",
            "limit": 2,
            "summary_type": "daily",
        })

    async def test_manual_script_record_memory_query_tools_find_saved_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            for tool, text in (
                ("note.add", "release report"),
                ("work_context.record", "implement Step 27 query"),
            ):
                await manual_tool_calls.run(manual_tool_calls.parse_args([
                    "--record-memory",
                    "--db-path",
                    str(db_path),
                    "--tool",
                    tool,
                    "--text",
                    text,
                ]))
            await manual_tool_calls.run(manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "summary.daily",
                "--date",
                "2026-06-22",
            ]))

            outputs = {}
            for tool, text in (
                ("note.search", "report"),
                ("work_context.query", "Step 27"),
                ("summary.query", manual_tool_calls.DEFAULT_TEXT),
            ):
                args = [
                    "--record-memory",
                    "--db-path",
                    str(db_path),
                    "--tool",
                    tool,
                    "--text",
                    text,
                    "--verbose",
                ]
                if tool == "summary.query":
                    args.extend(["--date", "2026-06-22"])
                outputs[tool] = await manual_tool_calls.run(
                    manual_tool_calls.parse_args(args),
                )

        for tool, output in outputs.items():
            action = next(
                item for item in output["result"]["executed_actions"]
                if item["name"] == tool
            )
            self.assertEqual(action["result"]["count"], 1)
        summary_action = next(
            item
            for item in outputs["summary.query"]["result"]["executed_actions"]
            if item["name"] == "summary.query"
        )
        summary_item = summary_action["result"]["items"][0]
        self.assertNotIn("content", summary_item)
        self.assertIn("content_preview", summary_item)

    async def test_manual_script_record_memory_task_add_outputs_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "task.add",
                "--text",
                "write tests",
            ])

            output = await manual_tool_calls.run(args)

        tasks = output["memory_snapshot"]["recent_tasks"]
        self.assertEqual(tasks[0]["title"], "write tests")
        self.assertEqual(tasks[0]["status"], "pending")

    async def test_manual_script_record_memory_task_query_returns_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            add_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "task.add",
                "--text",
                "write tests",
            ])
            await manual_tool_calls.run(add_args)

            query_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "task.query",
            ])
            output = await manual_tool_calls.run(query_args)

        query_action = next(action for action in output["result"]["executed_actions"] if action["name"] == "task.query")
        self.assertEqual(query_action["result"]["count"], 1)
        self.assertEqual(query_action["result"]["tasks"][0]["title"], "write tests")

    async def test_manual_script_record_memory_task_complete_marks_done(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            add_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "task.add",
                "--text",
                "write tests",
            ])
            await manual_tool_calls.run(add_args)

            complete_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "task.complete",
                "--text",
                "tests",
            ])
            output = await manual_tool_calls.run(complete_args)

        tasks = output["memory_snapshot"]["recent_tasks"]
        self.assertEqual(tasks[0]["title"], "write tests")
        self.assertEqual(tasks[0]["status"], "done")

    async def test_manual_script_record_memory_task_cancel_marks_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            add_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "task.add",
                "--text",
                "write tests",
            ])
            await manual_tool_calls.run(add_args)

            cancel_args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "task.cancel",
                "--text",
                "tests",
            ])
            output = await manual_tool_calls.run(cancel_args)

        tasks = output["memory_snapshot"]["recent_tasks"]
        self.assertEqual(tasks[0]["title"], "write tests")
        self.assertEqual(tasks[0]["status"], "cancelled")

    async def test_manual_script_compact_output_omits_full_memory_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "note.add",
                "--text",
                "compact note",
            ])
            output = await manual_tool_calls.run(args)

        compact = manual_tool_calls.format_output(output, verbose=False)

        self.assertIn("executed_action_names", compact)
        self.assertNotIn("memory_snapshot", compact)
        self.assertIn("memory_summary", compact)

    async def test_manual_script_verbose_output_includes_full_memory_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "note.add",
                "--text",
                "verbose note",
            ])
            output = await manual_tool_calls.run(args)

        verbose = manual_tool_calls.format_output(output, verbose=True)

        self.assertIn("memory_snapshot", verbose)
        self.assertIn("recent_notes", verbose["memory_snapshot"])

    async def test_manual_script_record_memory_compact_output_has_memory_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "note.add",
                "--text",
                "summary note",
            ])
            output = await manual_tool_calls.run(args)

        compact = manual_tool_calls.format_output(output, verbose=False)

        self.assertGreaterEqual(compact["memory_summary"]["recent_events_count"], 1)
        self.assertGreaterEqual(compact["memory_summary"]["recent_notes_count"], 1)
        self.assertIsInstance(compact["memory_summary"]["tool_run_summary"], dict)

    def test_manual_script_summary_daily_default_does_not_pass_today_date(self) -> None:
        tool_call = manual_tool_calls.build_tool_call("summary.daily", "summary")

        self.assertEqual(tool_call.arguments, {})

    async def test_manual_script_summary_daily_explicit_date_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "manual.db"
            args = manual_tool_calls.parse_args([
                "--record-memory",
                "--db-path",
                str(db_path),
                "--tool",
                "summary.daily",
                "--date",
                "2026-06-16",
            ])
            output = await manual_tool_calls.run(args)

        summaries = output["memory_snapshot"]["recent_summaries"]
        self.assertEqual(summaries[0]["date"], "2026-06-16")
        self.assertIn("2026-06-16", summaries[0]["title"])


if __name__ == "__main__":
    unittest.main()
