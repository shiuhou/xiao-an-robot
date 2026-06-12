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


if __name__ == "__main__":
    unittest.main()
