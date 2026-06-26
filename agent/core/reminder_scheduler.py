"""Legacy background scheduler for local reminder compatibility records."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall


class ReminderScheduler:
    """Poll legacy due reminders and trigger a robot.say action."""

    def __init__(
        self,
        memory_store: Any,
        robot_motion: Any = None,
        action_executor: Any = None,
        poll_interval_sec: float = 1.0,
        max_due_per_tick: int = 10,
    ):
        self.memory_store = memory_store
        self.robot_motion = robot_motion
        self.action_executor = action_executor
        self.poll_interval_sec = float(poll_interval_sec)
        self.max_due_per_tick = int(max_due_per_tick)

    async def tick(self) -> dict:
        due_reminders = self.memory_store.query_due_reminders(limit=self.max_due_per_tick)
        fired: list[dict] = []
        errors: list[dict] = []

        for reminder in due_reminders:
            reminder_id = reminder["id"]
            message = reminder["message"]
            try:
                trigger_result = await self._trigger_robot_say(message)
            except Exception as exc:
                errors.append({
                    "reminder_id": reminder_id,
                    "message": message,
                    "error": str(exc),
                })
                continue

            mark_result = self.memory_store.mark_reminder_fired(reminder_id)
            fired.append({
                "reminder_id": reminder_id,
                "message": message,
                "trigger_result": trigger_result,
                "mark_result": mark_result,
            })

        return {
            "fired_count": len(fired),
            "fired": fired,
            "errors": errors,
        }

    async def run_forever(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self.poll_interval_sec)

    def close(self) -> None:
        return None

    async def _trigger_robot_say(self, message: str) -> dict:
        if self.action_executor is not None:
            decision = OpenClawDecision(
                handled=True,
                tool_calls=[
                    OpenClawToolCall(
                        name="robot.say",
                        arguments={"text": message},
                    ),
                ],
            )
            try:
                return await self.action_executor.execute(
                    decision,
                    source_event_type="reminder.due",
                )
            except TypeError:
                return await self.action_executor.execute(decision)

        if self.robot_motion is None:
            raise RuntimeError("robot_motion or action_executor is required")

        result = self.robot_motion.say(message)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, dict) else {"result": result}
