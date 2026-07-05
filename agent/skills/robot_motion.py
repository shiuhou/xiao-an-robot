"""Robot motion skill for the local simulation MVP.

This skill intentionally has no OpenClaw dependency yet. It keeps a small,
OpenClaw-friendly class surface while delegating robot control to RobotGateway.
"""

from __future__ import annotations

import asyncio

from agent.core.gateway import RobotGateway


MIN_SAFE_SPEED = 0.52
MAX_SAFE_SPEED = 0.56
MAX_SAFE_DISTANCE_CM = 10.0
MAX_SAFE_TIMEOUT_MS = 2600
DEFAULT_SAFE_SPEED = 0.56
DEFAULT_SAFE_DISTANCE_CM = 10.0
DEFAULT_SAFE_TIMEOUT_MS = 1200
DEFAULT_MOVE_OUT_DURATION_MS = 2200
DEFAULT_MOVE_OUT_TIMEOUT_MS = 2600
DEFAULT_TURN_ANGLE_DEG = -25.0
DEFAULT_TURN_DURATION_MS = 450
DEFAULT_TURN_TIMEOUT_MS = 900
DEFAULT_POST_MOVE_DELAY_SEC = 2.35
DEFAULT_POST_TURN_DELAY_SEC = 0.7
DEFAULT_POST_EXPRESSION_DELAY_SEC = 0.4


def _clamp_number(value, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _clamp_motion_speed(value, default: float, minimum: float, maximum: float) -> float:
    speed = _clamp_number(value, default, 0.0, maximum)
    if speed <= 0.0:
        return 0.0
    return max(minimum, speed)


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
    duration_ms=None,
    timeout_ms=None,
    include_distance: bool = False,
    include_duration: bool = False,
    default_duration_ms: int | None = None,
    default_timeout_ms: int | None = None,
) -> tuple[dict, int]:
    params = {
        "speed": _clamp_motion_speed(speed, DEFAULT_SAFE_SPEED, MIN_SAFE_SPEED, MAX_SAFE_SPEED),
    }
    if include_distance:
        params["distance_cm"] = _clamp_number(
            distance_cm,
            DEFAULT_SAFE_DISTANCE_CM,
            0.0,
            MAX_SAFE_DISTANCE_CM,
        )
    if include_duration:
        params["duration_ms"] = _clamp_int(
            duration_ms,
            default_duration_ms or DEFAULT_MOVE_OUT_DURATION_MS,
            1,
            MAX_SAFE_TIMEOUT_MS,
        )
    return params, _clamp_int(
        timeout_ms,
        default_timeout_ms or DEFAULT_SAFE_TIMEOUT_MS,
        1,
        MAX_SAFE_TIMEOUT_MS,
    )


class RobotMotionSkill:
    """Send expression, motion, and TTS commands to the robot gateway."""

    name = "robot_motion"

    def __init__(
        self,
        gateway: RobotGateway | None = None,
        *,
        post_move_delay_sec: float = DEFAULT_POST_MOVE_DELAY_SEC,
        post_turn_delay_sec: float = DEFAULT_POST_TURN_DELAY_SEC,
        post_expression_delay_sec: float = DEFAULT_POST_EXPRESSION_DELAY_SEC,
    ):
        self.gateway = gateway or RobotGateway()
        self.post_move_delay_sec = max(0.0, float(post_move_delay_sec))
        self.post_turn_delay_sec = max(0.0, float(post_turn_delay_sec))
        self.post_expression_delay_sec = max(0.0, float(post_expression_delay_sec))

    async def show_expression(
        self,
        expression: str = "idle",
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
        duration_ms=None,
        timeout_ms=None,
    ) -> dict:
        params, safe_timeout_ms = safe_motion_params(
            speed=speed,
            distance_cm=distance_cm,
            duration_ms=duration_ms,
            timeout_ms=timeout_ms,
            include_distance=True,
            include_duration=True,
            default_duration_ms=DEFAULT_MOVE_OUT_DURATION_MS,
            default_timeout_ms=DEFAULT_MOVE_OUT_TIMEOUT_MS,
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

    async def turn_left(
        self,
        speed=None,
        angle_deg=None,
        duration_ms=None,
        timeout_ms=None,
    ) -> dict:
        params = {
            "speed": _clamp_motion_speed(speed, DEFAULT_SAFE_SPEED, MIN_SAFE_SPEED, MAX_SAFE_SPEED),
            "angle_deg": _clamp_number(angle_deg, DEFAULT_TURN_ANGLE_DEG, -360.0, 360.0),
            "duration_ms": _clamp_int(duration_ms, DEFAULT_TURN_DURATION_MS, 1, 10000),
        }
        return await self.gateway.send_motion(
            "turn",
            params=params,
            timeout_ms=_clamp_int(timeout_ms, DEFAULT_TURN_TIMEOUT_MS, 1, 10000),
        )

    async def say(self, text: str) -> dict:
        return await self.gateway.send_tts(text)

    async def care_for_user(
        self,
        text: str = "你已经工作很久了，休息一下吧。",
        speed=None,
        distance_cm=None,
        duration_ms=None,
        timeout_ms=None,
    ) -> list[dict]:
        results = []
        results.append(await self.move_out_of_dock(
            speed=speed,
            distance_cm=distance_cm,
            duration_ms=duration_ms,
            timeout_ms=timeout_ms,
        ))
        await asyncio.sleep(self.post_move_delay_sec)
        results.append(await self.turn_left(speed=speed))
        await asyncio.sleep(self.post_turn_delay_sec)
        results.append(await self.show_expression("caring"))
        await asyncio.sleep(self.post_expression_delay_sec)
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
        if action in {"turn_left", "left"}:
            return await self.turn_left(**params)
        if action == "say":
            return await self.say(**params)
        if action == "care_for_user":
            return await self.care_for_user(**params)

        return await self.gateway.send_motion(action, params=params)
