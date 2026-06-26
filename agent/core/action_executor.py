"""Execute OpenClaw decisions through local robot motion skills."""

from __future__ import annotations

import inspect
from typing import Any

from agent.core.local_tools import LocalToolRegistry
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall
from agent.core.project_memory import ProjectMemoryService
from agent.core.xiaoan_tool_manifest import XIAOAN_TOOL_NAMES


class ActionExecutor:
    """Apply OpenClaw decisions to the local robot execution layer."""

    RECOMMENDED_TOOL_NAMES = set(XIAOAN_TOOL_NAMES)

    LEGACY_ROBOT_TOOL_ALIASES = {
        "robot.say": "xiaoan.robot.say",
        "robot.expression": "xiaoan.robot.expression",
        "robot.move_out": "xiaoan.robot.move_out",
        "robot.move_out_of_dock": "xiaoan.robot.move_out",
        "robot.return_to_dock": "xiaoan.robot.return_to_dock",
        "robot.care": "xiaoan.robot.care",
        "robot.care_for_user": "xiaoan.robot.care",
    }

    LOCAL_TOOL_NAMES = {
        "note.add",
        "note.search",
        "work_context.record",
        "work_context.query",
        "summary.daily",
        "summary.query",
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
        project_memory_service: Any = None,
        emotion_snapshot_provider: Any = None,
        runtime_status_provider: Any = None,
    ):
        self.robot_motion_skill = robot_motion_skill
        self.memory_store = memory_store
        self.emotion_snapshot_provider = emotion_snapshot_provider
        self.runtime_status_provider = runtime_status_provider
        self.project_memory = (
            project_memory_service
            if project_memory_service is not None
            else (
                ProjectMemoryService(memory_store=memory_store)
                if memory_store is not None
                else None
            )
        )
        self.local_tool_registry = (
            local_tool_registry
            if local_tool_registry is not None
            else LocalToolRegistry(
                memory_store=memory_store,
                project_memory_service=self.project_memory,
            )
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
        canonical_name = self.LEGACY_ROBOT_TOOL_ALIASES.get(name, name)

        if canonical_name == "xiaoan.robot.say":
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
            executed_actions.append(self._executed(
                tool_call,
                result=self._xiaoan_success(canonical_name, result=result)
                if name == canonical_name
                else None,
            ))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._xiaoan_success(canonical_name, result=result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if canonical_name == "xiaoan.robot.expression":
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
                result = await self._call_expression(
                    expression=expression,
                    duration_ms=arguments.get("duration_ms"),
                    loop=arguments.get("loop"),
                )
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
            executed_actions.append(self._executed(
                tool_call,
                result=self._xiaoan_success(canonical_name, result=result)
                if name == canonical_name
                else None,
            ))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._xiaoan_success(canonical_name, result=result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if canonical_name == "xiaoan.robot.move_out":
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
            executed_actions.append(self._executed(
                tool_call,
                result=self._xiaoan_success(canonical_name, result=result)
                if name == canonical_name
                else None,
            ))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._xiaoan_success(canonical_name, result=result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if canonical_name == "xiaoan.robot.return_to_dock":
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
            executed_actions.append(self._executed(
                tool_call,
                result=self._xiaoan_success(canonical_name, result=result)
                if name == canonical_name
                else None,
            ))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._xiaoan_success(canonical_name, result=result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if canonical_name == "xiaoan.robot.care":
            text = arguments.get("text")
            try:
                result = await self._call(
                    self.robot_motion_skill.care_for_user,
                    text,
                ) if text else await self._call(
                    self.robot_motion_skill.care_for_user,
                )
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
            executed_actions.append(self._executed(
                tool_call,
                result=self._xiaoan_success(canonical_name, actions=result)
                if name == canonical_name
                else None,
            ))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=self._xiaoan_success(canonical_name, actions=result),
                status="success",
                source_event_type=source_event_type,
            )
            return

        if canonical_name == "xiaoan.breathing.start":
            try:
                result = await self._run_breathing(arguments)
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
            executed_actions.append(self._executed(tool_call, result=result))
            self._record_tool_run(
                tool_name=name,
                arguments=arguments,
                result=result,
                status="success",
                source_event_type=source_event_type,
            )
            return

        if canonical_name == "xiaoan.emotion.snapshot":
            result = await self._emotion_snapshot(arguments)
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
                skipped_action = self._skipped(tool_call, result.get("error", "emotion_store_unavailable"), result=result)
                skipped_actions.append(skipped_action)
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result=result,
                    status="failed",
                    error=str(result.get("error", "emotion_store_unavailable")),
                    source_event_type=source_event_type,
                )
            return

        if canonical_name == "xiaoan.runtime.status":
            result = await self._runtime_status()
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
                skipped_action = self._skipped(tool_call, result.get("error", "runtime_status_unavailable"), result=result)
                skipped_actions.append(skipped_action)
                self._record_tool_run(
                    tool_name=name,
                    arguments=arguments,
                    result=result,
                    status="failed",
                    error=str(result.get("error", "runtime_status_unavailable")),
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
                    status="failed",
                    error=str(result.get("error") or result.get("reason") or "local_tool_failed"),
                    source_event_type=source_event_type,
                )
            return

        skipped_action = self._skipped(tool_call, "unknown_tool")
        skipped_actions.append(skipped_action)
        self._record_tool_run(
            tool_name=name,
            arguments=arguments,
            result=skipped_action,
            status="failed",
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
    async def _call(function, *args, **kwargs):
        result = function(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _call_expression(
        self,
        expression: str,
        duration_ms: Any = None,
        loop: Any = None,
    ) -> dict:
        kwargs: dict[str, Any] = {}
        if duration_ms is not None:
            kwargs["duration_ms"] = int(duration_ms)
        if loop is not None:
            kwargs["loop"] = bool(loop)
        if not kwargs:
            return await self._call(self.robot_motion_skill.show_expression, expression)
        try:
            return await self._call(
                self.robot_motion_skill.show_expression,
                expression,
                **kwargs,
            )
        except TypeError:
            return await self._call(self.robot_motion_skill.show_expression, expression)

    async def _run_breathing(self, arguments: dict) -> dict:
        text = arguments.get("text") or "我们一起慢慢呼吸。吸气，停一下，再慢慢呼气。"
        actions = [
            await self._call_expression("calm"),
            await self._call(self.robot_motion_skill.say, text),
        ]
        return self._xiaoan_success("xiaoan.breathing.start", actions=actions)

    async def _emotion_snapshot(self, arguments: dict) -> dict:
        if self.emotion_snapshot_provider is None:
            return {
                "ok": False,
                "tool": "xiaoan.emotion.snapshot",
                "error": "emotion_store_unavailable",
            }
        seconds = int(arguments.get("seconds", 300) or 300)
        try:
            snapshot = await self._call(self.emotion_snapshot_provider, seconds=seconds)
        except TypeError:
            snapshot = await self._call(self.emotion_snapshot_provider, seconds)
        except Exception as exc:
            return {
                "ok": False,
                "tool": "xiaoan.emotion.snapshot",
                "error": str(exc) or "emotion_store_unavailable",
            }
        return {
            "ok": True,
            "tool": "xiaoan.emotion.snapshot",
            "snapshot": self._result_dict(snapshot),
        }

    async def _runtime_status(self) -> dict:
        if self.runtime_status_provider is None:
            return {
                "ok": False,
                "tool": "xiaoan.runtime.status",
                "error": "runtime_status_unavailable",
            }
        try:
            status = await self._call(self.runtime_status_provider)
        except Exception as exc:
            return {
                "ok": False,
                "tool": "xiaoan.runtime.status",
                "error": str(exc) or "runtime_status_unavailable",
            }
        return {
            "ok": True,
            "tool": "xiaoan.runtime.status",
            "status": self._result_dict(status),
        }

    @staticmethod
    def _xiaoan_success(
        tool_name: str,
        result: Any = None,
        actions: Any = None,
    ) -> dict:
        payload = {
            "ok": True,
            "tool": tool_name,
        }
        if actions is not None:
            payload["actions"] = actions
        else:
            payload["result"] = ActionExecutor._result_dict(result)
        return payload

    def _record_tool_run(
        self,
        tool_name: str,
        arguments: dict,
        result: dict,
        status: str,
        error: str | None = None,
        source_event_type: str | None = None,
    ) -> None:
        if self.project_memory is None:
            return
        record_tool_run = getattr(self.project_memory, "record_tool_run", None)
        if not callable(record_tool_run):
            return
        try:
            record_tool_run(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                ok=status == "success",
                source="openclaw",
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
