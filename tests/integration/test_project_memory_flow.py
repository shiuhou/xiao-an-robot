"""Regression tests for the complete project-memory write/read flow."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.action_executor import ActionExecutor
from agent.core.context_builder import ContextBuilder
from agent.core.memory import XiaoAnMemoryStore
from agent.core.memory_recorder import MemoryRecorder
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall
from agent.core.project_memory import ProjectMemoryService


class FakeRobotMotionSkill:
    def say(self, text: str) -> dict:
        return {"ok": True, "text": text}

    def show_expression(self, expression: str) -> dict:
        return {"ok": True, "expression": expression}

    def move_out_of_dock(self) -> dict:
        return {"ok": True}

    def return_to_dock(self) -> dict:
        return {"ok": True}


class ProjectMemoryFlowIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "project_memory_flow.db"
        self.store = XiaoAnMemoryStore(str(db_path))
        self.executor = ActionExecutor(
            FakeRobotMotionSkill(),
            memory_store=self.store,
        )
        self.builder = ContextBuilder(memory_store=self.store)
        self.recorder = MemoryRecorder(memory_store=self.store)

    async def asyncTearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    async def execute_tool(self, name: str, arguments: dict | None = None) -> dict:
        return await self.executor.execute(
            OpenClawDecision(
                handled=True,
                tool_calls=[OpenClawToolCall(name=name, arguments=arguments or {})],
            ),
            source_event_type="frontend.message",
        )

    def event_types(self) -> list[str]:
        return [
            event["event_type"]
            for event in self.store.query_recent_events(limit=50)
        ]

    async def test_note_add_success_flow(self) -> None:
        result = await self.execute_tool(
            "note.add",
            {"content": "remember the release decision", "tags": ["release"]},
        )

        self.assertEqual(result["executed_actions"][0]["name"], "note.add")
        self.assertEqual(
            self.store.query_recent_notes()[0]["content"],
            "remember the release decision",
        )
        self.assertIn("note.add", self.event_types())
        run = self.store.query_recent_tool_runs(tool_name="note.add")[0]
        self.assertEqual(run["status"], "success")

    async def test_work_context_record_success_flow(self) -> None:
        result = await self.execute_tool(
            "work_context.record",
            {
                "content": "editing project memory flow",
                "app_name": "VS Code",
                "activity_type": "coding",
            },
        )

        self.assertEqual(
            result["executed_actions"][0]["name"],
            "work_context.record",
        )
        activity = self.store.query_recent_work_activities()[0]
        self.assertEqual(activity["window_title"], "editing project memory flow")
        self.assertEqual(activity["app_name"], "VS Code")
        self.assertIn("work_context.record", self.event_types())
        run = self.store.query_recent_tool_runs(
            tool_name="work_context.record",
        )[0]
        self.assertEqual(run["status"], "success")

    async def test_summary_daily_success_flow(self) -> None:
        result = await self.execute_tool(
            "summary.daily",
            {"date": "2026-06-20"},
        )

        self.assertEqual(result["executed_actions"][0]["name"], "summary.daily")
        summary = self.store.query_recent_summaries()[0]
        self.assertEqual(summary["summary_type"], "daily")
        self.assertEqual(summary["date"], "2026-06-20")
        self.assertIn("summary.daily", self.event_types())
        run = self.store.query_recent_tool_runs(tool_name="summary.daily")[0]
        self.assertEqual(run["status"], "success")

    async def test_project_query_tools_read_written_memory(self) -> None:
        await self.execute_tool("note.add", {"content": "release report"})
        await self.execute_tool(
            "work_context.record",
            {"content": "implement Step 27 query", "app_name": "VS Code"},
        )
        await self.execute_tool("summary.daily", {"date": "2026-06-22"})

        note_result = await self.execute_tool(
            "note.search",
            {"keyword": "report"},
        )
        work_result = await self.execute_tool(
            "work_context.query",
            {"keyword": "Step 27"},
        )
        summary_result = await self.execute_tool(
            "summary.query",
            {"date": "2026-06-22"},
        )

        self.assertEqual(
            note_result["executed_actions"][0]["result"]["items"][0]["content"],
            "release report",
        )
        self.assertEqual(
            work_result["executed_actions"][0]["result"]["items"][0]["app_name"],
            "VS Code",
        )
        summary_item = summary_result["executed_actions"][0]["result"]["items"][0]
        self.assertNotIn("content", summary_item)
        self.assertIn("content_preview", summary_item)
        for tool_name in ("note.search", "work_context.query", "summary.query"):
            run = self.store.query_recent_tool_runs(tool_name=tool_name)[0]
            self.assertEqual(run["status"], "success")

    async def test_unknown_tool_failure_flow(self) -> None:
        result = await self.execute_tool(
            "unknown.tool",
            {"text": "manual failure"},
        )

        self.assertEqual(result["executed_actions"], [])
        self.assertEqual(result["skipped_actions"][0]["name"], "unknown.tool")
        self.assertEqual(
            result["skipped_actions"][0]["reason"],
            "unknown_tool",
        )
        run = self.store.query_recent_tool_runs(tool_name="unknown.tool")[0]
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "unknown_tool")

        events = self.store.query_recent_events(event_type="tool.run")
        unknown_event = next(
            event
            for event in events
            if event["payload"].get("tool_name") == "unknown.tool"
        )
        self.assertEqual(unknown_event["payload"]["error"], "unknown_tool")

    async def test_project_questions_read_recent_memory(self) -> None:
        await self.execute_tool(
            "note.add",
            {"content": "use ProjectMemoryService for project context"},
        )
        await self.execute_tool(
            "work_context.record",
            {
                "content": "writing Step 26 tests",
                "app_name": "VS Code",
                "activity_type": "coding",
            },
        )
        await self.execute_tool("summary.daily", {"date": "2026-06-20"})

        notes_context = self.builder.build_for_text("我刚才让你记了什么？")
        work_context = self.builder.build_for_text("我今天做了什么？")
        tools_context = self.builder.build_for_text("今天有哪些工具调用？")

        self.assertEqual(
            notes_context["project_memory"]["recent_notes"][0]["content"],
            "use ProjectMemoryService for project context",
        )
        self.assertEqual(
            work_context["project_memory"]["recent_work_activities"][0]["app_name"],
            "VS Code",
        )
        self.assertTrue(
            work_context["project_memory"]["recent_summaries"],
        )
        tool_names = {
            run["tool_name"]
            for run in tools_context["project_memory"]["recent_tool_runs"]
        }
        self.assertIn("note.add", tool_names)
        self.assertIn("work_context.record", tool_names)
        self.assertIn("summary.daily", tool_names)

    async def test_care_question_reads_step_25_events(self) -> None:
        self.recorder.record_companion_request(
            asr_text="我有点累",
            route="link_3_companion_fast_path",
            timestamp_ms=1000,
        )
        self.recorder.record_emotion_intervention(
            emotion_tag="tired",
            fatigue_score=82,
            route="link_2_emotion_fast_path",
            timestamp_ms=2000,
        )
        self.recorder.record_robot_care_action(
            action_name="care_for_user",
            route="link_2_emotion_fast_path",
            robot_action_result={"ok": True},
            timestamp_ms=3000,
        )

        context = self.builder.build_for_text("小安刚才有没有关心过我？")
        care_types = {
            event["event_type"]
            for event in context["project_memory"]["recent_care_events"]
        }

        self.assertEqual(care_types, {
            "companion.request",
            "emotion.intervention",
            "robot.care_action",
        })

    async def test_casual_questions_do_not_inject_project_memory(self) -> None:
        await self.execute_tool("note.add", {"content": "private project note"})

        for text in ("你好小安", "讲个笑话"):
            with self.subTest(text=text):
                context = self.builder.build_for_text(text)
                self.assertNotIn("project_memory", context)
                self.assertNotIn("notes", context)
                self.assertNotIn("summaries", context)

    async def test_daily_summary_is_previewed_not_injected_in_full(self) -> None:
        long_content = "full daily report detail " * 100
        ProjectMemoryService(memory_store=self.store).record_summary(
            long_content,
            payload={
                "title": "Long daily report",
                "date": "2026-06-20",
            },
        )

        context = self.builder.build_for_text("总结一下今天进展")
        project_summary = context["project_memory"]["recent_summaries"][0]
        legacy_summary = context["summaries"]["recent_summaries"][0]

        self.assertEqual(project_summary["title"], "Long daily report")
        self.assertLessEqual(len(project_summary["content_preview"]), 160)
        self.assertLessEqual(len(legacy_summary["content_preview"]), 160)
        self.assertNotEqual(project_summary["content_preview"], long_content)
        self.assertNotIn(long_content, repr(context))
        self.assertNotIn("payload_json", repr(context))
        self.assertNotIn("result_json", repr(context))

    async def test_task_and_reminder_questions_receive_lightweight_status(self) -> None:
        await self.execute_tool("task.add", {"title": "finish Step 27.5"})
        await self.execute_tool(
            "reminder.add",
            {"message": "review tests", "delay_seconds": 60},
        )

        task_context = self.builder.build_for_text("我还有哪些任务？")
        reminder_context = self.builder.build_for_text("有什么提醒？")

        self.assertEqual(
            task_context["project_memory"]["recent_tasks"][0]["title"],
            "finish Step 27.5",
        )
        self.assertEqual(
            task_context["project_memory"]["tasks_summary"]["pending_count"],
            1,
        )
        self.assertEqual(
            reminder_context["project_memory"]["recent_reminders"][0]["message"],
            "review tests",
        )
        self.assertEqual(
            reminder_context["project_memory"]["reminders_summary"][
                "pending_count"
            ],
            1,
        )
        self.assertNotIn("metadata_json", repr(reminder_context))


if __name__ == "__main__":
    unittest.main()
