"""Execute OpenClaw decisions through local robot motion skills."""

from __future__ import annotations

import inspect
from typing import Any

from agent.core.local_tools import LocalToolRegistry
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall


class ActionExecutor:
    """Apply OpenClaw decisions to the local robot execution layer."""

    LOCAL_TOOL_NAMES = {
        "note.add",
        "work_context.record",
        "summary.daily",
        "reminder.add",
        "reminder.query",
        "reminder.cancel",
        "task.add",
        "task.query",
        "task.complete",
        "task.cancel",
    }

    def __init__(
        self,
        robot_motion_skill: Any = None,
        local_tool_registry: Any = None,
        memory_store: Any = None,
    ):
        self.robot_motion_skill = robot_motion_skill
        self.memory_store = memory_store
        self.local_tool_registry = (
            local_tool_registry
            if local_tool_registry is not None
            else LocalToolRegistry(memory_store=memory_store)
        )

    async def execute(self, decision: OpenClawDecision, source_event_type: str | None = None) -> dict:
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
            try:
                result = await self._call(self.robot_motion_skill.say, decision.reply_text)
            except Exception as exc:
                self._record_tool_run(
                    tool_name="robot.say",
                    arguments=arguments,
                    result={},
                    status="failed",
                    error=str(exc),
                    source_event_type=source_event_type,
                )
                raise
            executed_actions.append({
                "name": "robot.say",
                "source": "reply_text",
                "arguments": arguments,
            })
            self._record_tool_run(
                tool_name="robot.say",
                arguments=arguments,
                result=self._result_dict(result),
                status="success",
                source_event_type=source_event_type,
            )

        for tool_call in decision.tool_calls:
            await self._execute_tool_call(
                tool_call,
                executed_actions,
                skipped_actions,
                source_event_type=source_event_type,
            )

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
        source_event_type: str | None = None,
    ) -> None:
        name = tool_call.name
        arguments = dict(tool_call.arguments)

        if name == "robot.say":
            text = arguments.get("text")
            if not text:
                skipped_action = self._skipped(tool_call, "missing_text")
                skipped_actions.append(skipped_action)
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result=skipped_action,
                    status="skipped",
                    error="missing_text",
                    source_event_type=source_event_type,
                )
                return
            try:
                result = await self._call(self.robot_motion_skill.say, text)
            except Exception as exc:
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result={},
                    status="failed",
                    error=str(exc),
                    source_event_type=source_event_type,
                )
                raise
            executed_actions.append(self._executed(tool_call))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._result_dict(result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if name == "robot.expression":
            expression = arguments.get("expression")
            if not expression:
                skipped_action = self._skipped(tool_call, "missing_expression")
                skipped_actions.append(skipped_action)
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result=skipped_action,
                    status="skipped",
                    error="missing_expression",
                    source_event_type=source_event_type,
                )
                return
            try:
                result = await self._call(self.robot_motion_skill.show_expression, expression)
            except Exception as exc:
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result={},
                    status="failed",
                    error=str(exc),
                    source_event_type=source_event_type,
                )
                raise
            executed_actions.append(self._executed(tool_call))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._result_dict(result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if name == "robot.move_out_of_dock":
            try:
                result = await self._call(self.robot_motion_skill.move_out_of_dock)
            except Exception as exc:
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result={},
                    status="failed",
                    error=str(exc),
                    source_event_type=source_event_type,
                )
                raise
            executed_actions.append(self._executed(tool_call))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._result_dict(result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if name == "robot.return_to_dock":
            try:
                result = await self._call(self.robot_motion_skill.return_to_dock)
            except Exception as exc:
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result={},
                    status="failed",
                    error=str(exc),
                    source_event_type=source_event_type,
                )
                raise
            executed_actions.append(self._executed(tool_call))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._result_dict(result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if name in self.LOCAL_TOOL_NAMES:
            try:
                result = self.local_tool_registry.execute(name, arguments)
            except Exception as exc:
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result={},
                    status="failed",
                    error=str(exc),
                    source_event_type=source_event_type,
                )
                raise
            if result.get("ok", False):
                executed_actions.append(self._executed(tool_call, result=result))
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result=result,
                    status="success",
                    source_event_type=source_event_type,
                )
            else:
                skipped_action = self._skipped(tool_call, "local_tool_failed", result=result)
                skipped_actions.append(skipped_action)
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result=result,
                    status="skipped",
                    error="local_tool_failed",
                    source_event_type=source_event_type,
                )
            return

        skipped_action = self._skipped(tool_call, "unknown_tool")
        skipped_actions.append(skipped_action)
        self._record_tool_run(
            tool_name=name,
            arguments=arguments,
            result=skipped_action,
            status="skipped",
            error="unknown_tool",
            source_event_type=source_event_type,
        )

    @staticmethod
    def _executed(tool_call: OpenClawToolCall, result: dict | None = None) -> dict:
        action = {
            "name": tool_call.name,
            "source": "tool_call",
            "arguments": dict(tool_call.arguments),
        }
        if result is not None:
            action["result"] = result
        return action

    @staticmethod
    def _skipped(tool_call: OpenClawToolCall, reason: str, result: dict | None = None) -> dict:
        action = {
            "name": tool_call.name,
            "reason": reason,
            "arguments": dict(tool_call.arguments),
        }
        if result is not None:
            action["result"] = result
        return action

    @staticmethod
    async def _call(function, *args):
        result = function(*args)
        if inspect.isawaitable(result):
            return await result
        return result

    def _record_tool_run(
        self,
        tool_name: str,
        arguments: dict,
        result: dict,
        status: str,
        error: str | None = None,
        source_event_type: str | None = None,
    ) -> None:
        if self.memory_store is None:
            return
        insert_tool_run = getattr(self.memory_store, "insert_tool_run", None)
        if not callable(insert_tool_run):
            return
        try:
            insert_tool_run(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                status=status,
                error=error,
                source_event_type=source_event_type,
            )
        except Exception:
            return

    @staticmethod
    def _result_dict(result: Any) -> dict:
        if isinstance(result, dict):
            return result
        if result is None:
            return {}
        return {"result": result}
