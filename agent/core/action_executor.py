"""Execute OpenClaw decisions through local robot motion skills."""

from __future__ import annotations

import inspect
from typing import Any

from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall


class ActionExecutor:
    """Apply OpenClaw decisions to the local robot execution layer."""

    def __init__(self, robot_motion_skill: Any):
        self.robot_motion_skill = robot_motion_skill

    async def execute(self, decision: OpenClawDecision) -> dict:
        executed_actions: list[dict] = []
        skipped_actions: list[dict] = []

        if not decision.handled:
            return {
                "handled": False,
                "reply_text": decision.reply_text,
                "executed_actions": executed_actions,
                "skipped_actions": skipped_actions,
            }

        if decision.reply_text:
            arguments = {"text": decision.reply_text}
            await self._call(self.robot_motion_skill.say, decision.reply_text)
            executed_actions.append({
                "name": "robot.say",
                "source": "reply_text",
                "arguments": arguments,
            })

        for tool_call in decision.tool_calls:
            await self._execute_tool_call(tool_call, executed_actions, skipped_actions)

        return {
            "handled": True,
            "reply_text": decision.reply_text,
            "executed_actions": executed_actions,
            "skipped_actions": skipped_actions,
        }

    async def _execute_tool_call(
        self,
        tool_call: OpenClawToolCall,
        executed_actions: list[dict],
        skipped_actions: list[dict],
    ) -> None:
        name = tool_call.name
        arguments = dict(tool_call.arguments)

        if name == "robot.say":
            text = arguments.get("text")
            if not text:
                skipped_actions.append(self._skipped(tool_call, "missing_text"))
                return
            await self._call(self.robot_motion_skill.say, text)
            executed_actions.append(self._executed(tool_call))
            return

        if name == "robot.expression":
            expression = arguments.get("expression")
            if not expression:
                skipped_actions.append(self._skipped(tool_call, "missing_expression"))
                return
            await self._call(self.robot_motion_skill.show_expression, expression)
            executed_actions.append(self._executed(tool_call))
            return

        if name == "robot.move_out_of_dock":
            await self._call(self.robot_motion_skill.move_out_of_dock)
            executed_actions.append(self._executed(tool_call))
            return

        if name == "robot.return_to_dock":
            await self._call(self.robot_motion_skill.return_to_dock)
            executed_actions.append(self._executed(tool_call))
            return

        skipped_actions.append(self._skipped(tool_call, "unknown_tool"))

    @staticmethod
    def _executed(tool_call: OpenClawToolCall) -> dict:
        return {
            "name": tool_call.name,
            "source": "tool_call",
            "arguments": dict(tool_call.arguments),
        }

    @staticmethod
    def _skipped(tool_call: OpenClawToolCall, reason: str) -> dict:
        return {
            "name": tool_call.name,
            "reason": reason,
            "arguments": dict(tool_call.arguments),
        }

    @staticmethod
    async def _call(function, *args):
        result = function(*args)
        if inspect.isawaitable(result):
            return await result
        return result
