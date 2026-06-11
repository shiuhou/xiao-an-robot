"""Robot motion skill for the local simulation MVP.

This skill intentionally has no OpenClaw dependency yet. It keeps a small,
OpenClaw-friendly class surface while delegating robot control to RobotGateway.
"""

from __future__ import annotations

from agent.core.gateway import RobotGateway


class RobotMotionSkill:
    """Send expression, motion, and TTS commands to the robot gateway."""

    name = "robot_motion"

    def __init__(self, gateway: RobotGateway | None = None):
        self.gateway = gateway or RobotGateway()

    async def show_expression(
        self,
        expression: str = "neutral",
        duration_ms: int = 3000,
        loop: bool = False,
    ) -> dict:
        return await self.gateway.send_expression(
            expression,
            duration_ms=duration_ms,
            loop=loop,
        )

    async def move_out_of_dock(self) -> dict:
        return await self.gateway.send_motion("move_out_of_dock")

    async def return_to_dock(self) -> dict:
        return await self.gateway.send_motion("move_back_to_dock")

    async def say(self, text: str) -> dict:
        return await self.gateway.send_tts(text)

    async def care_for_user(self, text: str = "你已经工作很久了，休息一下吧。") -> list[dict]:
        results = []
        results.append(await self.show_expression("caring"))
        results.append(await self.move_out_of_dock())
        results.append(await self.say(text))
        return results

    async def run(self, action: str, params: dict | None = None):
        """Compatibility entry point for future OpenClaw skill invocation."""

        params = params or {}
        if action == "show_expression":
            return await self.show_expression(**params)
        if action == "move_out_of_dock":
            return await self.move_out_of_dock()
        if action in {"return_to_dock", "move_back_to_dock"}:
            return await self.return_to_dock()
        if action == "say":
            return await self.say(**params)
        if action == "care_for_user":
            return await self.care_for_user(**params)

        return await self.gateway.send_motion(action, params=params)
