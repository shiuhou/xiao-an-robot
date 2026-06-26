"""Robot motion skill for the local simulation MVP.

This skill intentionally has no OpenClaw dependency yet. It keeps a small,
OpenClaw-friendly class surface while delegating robot control to RobotGateway.
"""

from __future__ import annotations

from agent.core.gateway import RobotGateway


MAX_SAFE_SPEED = 0.2
MAX_SAFE_DISTANCE_CM = 2.0
MAX_SAFE_TIMEOUT_MS = 500
DEFAULT_SAFE_SPEED = 0.2
DEFAULT_SAFE_DISTANCE_CM = 2.0
DEFAULT_SAFE_TIMEOUT_MS = 500


def _clamp_number(value, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _clamp_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def safe_motion_params(
    *,
    speed=None,
    distance_cm=None,
    timeout_ms=None,
    include_distance: bool = False,
) -> tuple[dict, int]:
    params = {
        "speed": _clamp_number(speed, DEFAULT_SAFE_SPEED, 0.0, MAX_SAFE_SPEED),
    }
    if include_distance:
        params["distance_cm"] = _clamp_number(
            distance_cm,
            DEFAULT_SAFE_DISTANCE_CM,
            0.0,
            MAX_SAFE_DISTANCE_CM,
        )
    return params, _clamp_int(timeout_ms, DEFAULT_SAFE_TIMEOUT_MS, 1, MAX_SAFE_TIMEOUT_MS)


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

    async def move_out_of_dock(
        self,
        speed=None,
        distance_cm=None,
        timeout_ms=None,
    ) -> dict:
        params, safe_timeout_ms = safe_motion_params(
            speed=speed,
            distance_cm=distance_cm,
            timeout_ms=timeout_ms,
            include_distance=True,
        )
        return await self.gateway.send_motion(
            "move_out_of_dock",
            params=params,
            timeout_ms=safe_timeout_ms,
        )

    async def return_to_dock(self, speed=None, timeout_ms=None) -> dict:
        params, safe_timeout_ms = safe_motion_params(
            speed=speed,
            timeout_ms=timeout_ms,
            include_distance=False,
        )
        return await self.gateway.send_motion(
            "move_back_to_dock",
            params=params,
            timeout_ms=safe_timeout_ms,
        )

    async def say(self, text: str) -> dict:
        return await self.gateway.send_tts(text)

    async def care_for_user(
        self,
        text: str = "你已经工作很久了，休息一下吧。",
        speed=None,
        distance_cm=None,
        timeout_ms=None,
    ) -> list[dict]:
        results = []
        results.append(await self.show_expression("caring"))
        results.append(await self.move_out_of_dock(
            speed=speed,
            distance_cm=distance_cm,
            timeout_ms=timeout_ms,
        ))
        results.append(await self.say(text))
        return results

    async def run(self, action: str, params: dict | None = None):
        """Compatibility entry point for future OpenClaw skill invocation."""

        params = params or {}
        if action == "show_expression":
            return await self.show_expression(**params)
        if action == "move_out_of_dock":
            return await self.move_out_of_dock(**params)
        if action in {"return_to_dock", "move_back_to_dock"}:
            return await self.return_to_dock(
                speed=params.get("speed"),
                timeout_ms=params.get("timeout_ms"),
            )
        if action == "say":
            return await self.say(**params)
        if action == "care_for_user":
            return await self.care_for_user(**params)

        return await self.gateway.send_motion(action, params=params)
