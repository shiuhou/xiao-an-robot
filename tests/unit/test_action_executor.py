"""Unit tests for ActionExecutor."""

from __future__ import annotations

import unittest

from agent.core.action_executor import ActionExecutor
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall


class FakeRobotMotionSkill:
    def __init__(self) -> None:
        self.say_calls = []
        self.expression_calls = []
        self.move_out_calls = 0
        self.return_to_dock_calls = 0

    def say(self, text: str) -> dict:
        self.say_calls.append(text)
        return {"ok": True}

    def show_expression(self, expression: str) -> dict:
        self.expression_calls.append(expression)
        return {"ok": True}

    def move_out_of_dock(self) -> dict:
        self.move_out_calls += 1
        return {"ok": True}

    def return_to_dock(self) -> dict:
        self.return_to_dock_calls += 1
        return {"ok": True}


class FailingRobotMotionSkill(FakeRobotMotionSkill):
    def say(self, text: str) -> dict:
        raise RuntimeError("say failed")


class AsyncFakeRobotMotionSkill(FakeRobotMotionSkill):
    async def say(self, text: str) -> dict:
        self.say_calls.append(text)
        return {"ok": True}

    async def show_expression(self, expression: str) -> dict:
        self.expression_calls.append(expression)
        return {"ok": True}

    async def move_out_of_dock(self) -> dict:
        self.move_out_calls += 1
        return {"ok": True}

    async def return_to_dock(self) -> dict:
        self.return_to_dock_calls += 1
        return {"ok": True}


class FakeLocalToolRegistry:
    def __init__(self, result: dict | None = None, raise_error: bool = False) -> None:
        self.calls = []
        self.result = result
        self.raise_error = raise_error

    def execute(self, name: str, arguments: dict | None = None) -> dict:
        self.calls.append((name, arguments))
        if self.raise_error:
            raise RuntimeError("local tool failed hard")
        if self.result is not None:
            return self.result
        return {
            "ok": True,
            "name": name,
            "result": arguments or {},
        }


class FakeMemoryStore:
    def __init__(self, raise_error: bool = False) -> None:
        self.raise_error = raise_error
        self.tool_runs = []
        self.notes = []
        self.summaries = []
        self.reminders = []
        self.tasks = []

    def insert_tool_run(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        self.tool_runs.append(kwargs)
        return {"event_id": len(self.tool_runs), "tool_run_id": len(self.tool_runs)}

    def insert_note(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        self.notes.append(kwargs)
        return {"event_id": len(self.notes), "note_id": len(self.notes)}

    def insert_summary(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        self.summaries.append(kwargs)
        return {"event_id": len(self.summaries), "summary_id": len(self.summaries)}

    def insert_reminder(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        reminder = dict(kwargs)
        reminder["id"] = len(self.reminders) + 1
        reminder["status"] = "pending"
        self.reminders.append(reminder)
        return {"event_id": len(self.reminders), "reminder_id": len(self.reminders), "due_at_ms": 1234}

    def query_reminders(self, limit: int = 20, status: str | None = None, include_fired: bool = False) -> list[dict]:
        reminders = self.reminders
        if status is not None:
            reminders = [item for item in reminders if item.get("status") == status]
        elif not include_fired:
            reminders = [item for item in reminders if item.get("status") == "pending"]
        return reminders[:limit]

    def cancel_reminder(self, reminder_id=None, message_contains=None, **kwargs) -> dict:
        for reminder in self.reminders:
            id_matches = reminder_id is not None and reminder["id"] == int(reminder_id)
            text_matches = message_contains and message_contains in reminder["message"]
            if reminder.get("status") == "pending" and (id_matches or text_matches):
                reminder["status"] = "cancelled"
                return {"ok": True, "event_id": 99, "reminder_id": reminder["id"], "message": reminder["message"]}
        return {"ok": False, "reason": "not_found"}

    def insert_task(self, **kwargs) -> dict:
        if self.raise_error:
            raise RuntimeError("memory unavailable")
        task = dict(kwargs)
        task["id"] = len(self.tasks) + 1
        task["status"] = "pending"
        self.tasks.append(task)
        return {"event_id": len(self.tasks), "task_id": len(self.tasks)}

    def query_tasks(self, limit: int = 20, status: str | None = None, project_hint=None, include_done: bool = False):
        tasks = self.tasks
        if status is not None:
            tasks = [item for item in tasks if item.get("status") == status]
        elif not include_done:
            tasks = [item for item in tasks if item.get("status") == "pending"]
        return tasks[:limit]

    def complete_task(self, task_id=None, title_contains=None, **kwargs) -> dict:
        return self._set_task_status("done", task_id=task_id, title_contains=title_contains)

    def cancel_task(self, task_id=None, title_contains=None, **kwargs) -> dict:
        return self._set_task_status("cancelled", task_id=task_id, title_contains=title_contains)

    def _set_task_status(self, status: str, task_id=None, title_contains=None) -> dict:
        for task in self.tasks:
            id_matches = task_id is not None and task["id"] == int(task_id)
            text_matches = title_contains and title_contains in task["title"]
            if task.get("status") == "pending" and (id_matches or text_matches):
                task["status"] = status
                return {"ok": True, "event_id": 100, "task_id": task["id"], "title": task["title"]}
        return {"ok": False, "reason": "not_found"}

    def get_recent_work_summary(self) -> dict:
        return {"count": 2}

    def get_notes_summary(self) -> dict:
        return {"count": len(self.notes)}

    def get_tool_run_summary(self) -> dict:
        return {"count": len(self.tool_runs)}


class ActionExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_unhandled_decision_executes_nothing(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)

        result = await executor.execute(OpenClawDecision(handled=False, reply_text="ignored"))

        self.assertFalse(result["handled"])
        self.assertEqual(result["reply_text"], "ignored")
        self.assertEqual(result["executed_actions"], [])
        self.assertEqual(result["skipped_actions"], [])
        self.assertEqual(robot_motion.say_calls, [])
        self.assertEqual(robot_motion.expression_calls, [])
        self.assertEqual(robot_motion.move_out_calls, 0)
        self.assertEqual(robot_motion.return_to_dock_calls, 0)

    async def test_unhandled_decision_does_not_call_local_tool_registry(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        local_tools = FakeLocalToolRegistry()
        executor = ActionExecutor(robot_motion, local_tool_registry=local_tools)
        decision = OpenClawDecision(
            handled=False,
            tool_calls=[OpenClawToolCall(name="note.add", arguments={"content": "ignored"})],
        )

        result = await executor.execute(decision)

        self.assertFalse(result["handled"])
        self.assertEqual(local_tools.calls, [])

    async def test_reply_text_calls_say_and_records_action(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)

        result = await executor.execute(OpenClawDecision(handled=True, reply_text="hello"))

        self.assertEqual(robot_motion.say_calls, ["hello"])
        self.assertEqual(result["executed_actions"], [{
            "name": "robot.say",
            "source": "reply_text",
            "arguments": {"text": "hello"},
        }])

    async def test_robot_say_tool_call_calls_say(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.say", arguments={"text": "hello"})],
        )

        result = await executor.execute(decision)

        self.assertEqual(robot_motion.say_calls, ["hello"])
        self.assertEqual(result["executed_actions"][0]["name"], "robot.say")
        self.assertEqual(result["executed_actions"][0]["source"], "tool_call")

    async def test_robot_expression_tool_call_calls_show_expression(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.expression", arguments={"expression": "happy"})],
        )

        await executor.execute(decision)

        self.assertEqual(robot_motion.expression_calls, ["happy"])

    async def test_robot_move_out_of_dock_tool_call_calls_motion(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.move_out_of_dock")],
        )

        await executor.execute(decision)

        self.assertEqual(robot_motion.move_out_calls, 1)

    async def test_robot_return_to_dock_tool_call_calls_motion(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.return_to_dock")],
        )

        await executor.execute(decision)

        self.assertEqual(robot_motion.return_to_dock_calls, 1)

    async def test_unknown_tool_is_skipped_without_crashing(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.unknown", arguments={"x": 1})],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"], [])
        self.assertEqual(result["skipped_actions"], [{
            "name": "robot.unknown",
            "reason": "unknown_tool",
            "arguments": {"x": 1},
        }])

    async def test_note_add_tool_call_uses_local_tool_registry(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        local_tools = FakeLocalToolRegistry()
        executor = ActionExecutor(robot_motion, local_tool_registry=local_tools)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="note.add", arguments={"content": "hello"})],
        )

        result = await executor.execute(decision)

        self.assertEqual(local_tools.calls, [("note.add", {"content": "hello"})])
        self.assertEqual(result["executed_actions"][0]["name"], "note.add")
        self.assertEqual(result["executed_actions"][0]["source"], "tool_call")
        self.assertEqual(result["executed_actions"][0]["result"]["ok"], True)

    async def test_work_context_record_tool_call_uses_local_tool_registry(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        local_tools = FakeLocalToolRegistry()
        executor = ActionExecutor(robot_motion, local_tool_registry=local_tools)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="work_context.record", arguments={"content": "coding"})],
        )

        result = await executor.execute(decision)

        self.assertEqual(local_tools.calls, [("work_context.record", {"content": "coding"})])
        self.assertEqual(result["executed_actions"][0]["name"], "work_context.record")

    async def test_summary_daily_tool_call_uses_local_tool_registry(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        local_tools = FakeLocalToolRegistry()
        executor = ActionExecutor(robot_motion, local_tool_registry=local_tools)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="summary.daily", arguments={"date": "2026-06-13"})],
        )

        result = await executor.execute(decision)

        self.assertEqual(local_tools.calls, [("summary.daily", {"date": "2026-06-13"})])
        self.assertEqual(result["executed_actions"][0]["name"], "summary.daily")

    async def test_local_tool_ok_false_goes_to_skipped_actions(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        local_tools = FakeLocalToolRegistry(result={
            "ok": False,
            "name": "note.add",
            "error": "failed",
        })
        executor = ActionExecutor(robot_motion, local_tool_registry=local_tools)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="note.add", arguments={"content": "hello"})],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"], [])
        self.assertEqual(result["skipped_actions"][0]["name"], "note.add")
        self.assertEqual(result["skipped_actions"][0]["reason"], "local_tool_failed")
        self.assertEqual(result["skipped_actions"][0]["result"]["error"], "failed")

    async def test_robot_say_missing_text_is_skipped(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.say")],
        )

        result = await executor.execute(decision)

        self.assertEqual(robot_motion.say_calls, [])
        self.assertEqual(result["skipped_actions"][0]["reason"], "missing_text")

    async def test_robot_expression_missing_expression_is_skipped(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.expression")],
        )

        result = await executor.execute(decision)

        self.assertEqual(robot_motion.expression_calls, [])
        self.assertEqual(result["skipped_actions"][0]["reason"], "missing_expression")

    async def test_async_robot_motion_say_is_awaited(self) -> None:
        robot_motion = AsyncFakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)

        result = await executor.execute(OpenClawDecision(handled=True, reply_text="hello"))

        self.assertEqual(robot_motion.say_calls, ["hello"])
        self.assertEqual(result["executed_actions"][0]["name"], "robot.say")

    async def test_async_robot_motion_move_out_of_dock_is_awaited(self) -> None:
        robot_motion = AsyncFakeRobotMotionSkill()
        executor = ActionExecutor(robot_motion)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.move_out_of_dock")],
        )

        result = await executor.execute(decision)

        self.assertEqual(robot_motion.move_out_calls, 1)
        self.assertEqual(result["executed_actions"][0]["name"], "robot.move_out_of_dock")

    async def test_reply_text_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)

        await executor.execute(OpenClawDecision(handled=True, reply_text="hello"))

        self.assertEqual(len(memory_store.tool_runs), 1)
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "robot.say")
        self.assertEqual(memory_store.tool_runs[0]["arguments"], {"text": "hello"})
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")

    async def test_robot_say_tool_call_records_success(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.say", arguments={"text": "hello"})],
        )

        await executor.execute(decision, source_event_type="asr.transcript")

        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "robot.say")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")
        self.assertEqual(memory_store.tool_runs[0]["source_event_type"], "asr.transcript")

    async def test_local_tool_success_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        local_tools = FakeLocalToolRegistry()
        executor = ActionExecutor(
            FakeRobotMotionSkill(),
            local_tool_registry=local_tools,
            memory_store=memory_store,
        )
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="note.add", arguments={"content": "hello"})],
        )

        await executor.execute(decision)

        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "note.add")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")
        self.assertEqual(memory_store.tool_runs[0]["result"]["ok"], True)

    async def test_unknown_tool_records_skipped(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="robot.unknown", arguments={"x": 1})],
        )

        await executor.execute(decision)

        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "robot.unknown")
        self.assertEqual(memory_store.tool_runs[0]["status"], "skipped")
        self.assertEqual(memory_store.tool_runs[0]["error"], "unknown_tool")

    async def test_local_tool_ok_false_records_skipped(self) -> None:
        memory_store = FakeMemoryStore()
        local_tools = FakeLocalToolRegistry(result={
            "ok": False,
            "name": "note.add",
            "error": "failed",
        })
        executor = ActionExecutor(
            FakeRobotMotionSkill(),
            local_tool_registry=local_tools,
            memory_store=memory_store,
        )
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="note.add", arguments={"content": "hello"})],
        )

        await executor.execute(decision)

        self.assertEqual(memory_store.tool_runs[0]["status"], "skipped")
        self.assertEqual(memory_store.tool_runs[0]["error"], "local_tool_failed")

    async def test_tool_execution_failure_records_failed_and_reraises(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FailingRobotMotionSkill(), memory_store=memory_store)

        with self.assertRaises(RuntimeError):
            await executor.execute(OpenClawDecision(handled=True, reply_text="hello"))

        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "robot.say")
        self.assertEqual(memory_store.tool_runs[0]["status"], "failed")
        self.assertIn("say failed", memory_store.tool_runs[0]["error"])

    async def test_memory_store_failure_does_not_break_execution(self) -> None:
        robot_motion = FakeRobotMotionSkill()
        memory_store = FakeMemoryStore(raise_error=True)
        executor = ActionExecutor(robot_motion, memory_store=memory_store)

        result = await executor.execute(OpenClawDecision(handled=True, reply_text="hello"))

        self.assertEqual(robot_motion.say_calls, ["hello"])
        self.assertEqual(result["executed_actions"][0]["name"], "robot.say")

    async def test_default_local_tool_registry_receives_memory_store_for_note_add(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="note.add", arguments={"content": "hello"})],
        )

        result = await executor.execute(decision)

        self.assertEqual(memory_store.notes[0]["content"], "hello")
        self.assertEqual(result["executed_actions"][0]["name"], "note.add")
        self.assertTrue(result["executed_actions"][0]["result"]["result"]["persisted"])

    async def test_note_add_persists_note_and_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[OpenClawToolCall(name="note.add", arguments={"content": "hello"})],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"][0]["name"], "note.add")
        self.assertEqual(memory_store.notes[0]["content"], "hello")
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "note.add")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")

    async def test_work_context_record_persists_note_and_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="work_context.record",
                    arguments={"content": "coding", "project_hint": "xiao-an-robot"},
                )
            ],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"][0]["name"], "work_context.record")
        self.assertEqual(memory_store.notes[0]["content"], "coding")
        self.assertEqual(memory_store.notes[0]["tags"], ["work_context"])
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "work_context.record")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")

    async def test_summary_daily_persists_summary_and_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="summary.daily",
                    arguments={"date": "2026-06-16"},
                )
            ],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"][0]["name"], "summary.daily")
        self.assertEqual(memory_store.summaries[0]["summary_type"], "daily")
        self.assertEqual(memory_store.summaries[0]["date"], "2026-06-16")
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "summary.daily")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")

    async def test_reminder_add_executes_and_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="reminder.add",
                    arguments={"message": "wake me", "delay_seconds": 60},
                )
            ],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"][0]["name"], "reminder.add")
        self.assertEqual(memory_store.reminders[0]["message"], "wake me")
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "reminder.add")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")

    async def test_reminder_cancel_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        memory_store.insert_reminder(message="wake me", delay_seconds=60)
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="reminder.cancel",
                    arguments={"message_contains": "wake"},
                )
            ],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"][0]["name"], "reminder.cancel")
        self.assertEqual(memory_store.reminders[0]["status"], "cancelled")
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "reminder.cancel")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")

    async def test_task_add_executes_and_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="task.add",
                    arguments={"title": "write tests"},
                )
            ],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"][0]["name"], "task.add")
        self.assertEqual(memory_store.tasks[0]["title"], "write tests")
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "task.add")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")

    async def test_task_complete_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        memory_store.insert_task(title="write tests")
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="task.complete",
                    arguments={"title_contains": "tests"},
                )
            ],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"][0]["name"], "task.complete")
        self.assertEqual(memory_store.tasks[0]["status"], "done")
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "task.complete")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")

    async def test_task_cancel_records_tool_run(self) -> None:
        memory_store = FakeMemoryStore()
        memory_store.insert_task(title="write tests")
        executor = ActionExecutor(FakeRobotMotionSkill(), memory_store=memory_store)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="task.cancel",
                    arguments={"title_contains": "tests"},
                )
            ],
        )

        result = await executor.execute(decision)

        self.assertEqual(result["executed_actions"][0]["name"], "task.cancel")
        self.assertEqual(memory_store.tasks[0]["status"], "cancelled")
        self.assertEqual(memory_store.tool_runs[0]["tool_name"], "task.cancel")
        self.assertEqual(memory_store.tool_runs[0]["status"], "success")


if __name__ == "__main__":
    unittest.main()
