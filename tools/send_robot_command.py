"""Send local Agent commands to the base station /agent WebSocket channel.

This is a development-only CLI for the first local simulation MVP:
Agent -> BaseStation -> MockRobot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any


DEFAULT_AGENT_URL = "ws://127.0.0.1:8765/agent"
MIN_SAFE_SPEED = 0.52
MAX_SAFE_SPEED = 0.56
MAX_SAFE_DISTANCE_CM = 10.0
MAX_SAFE_TIMEOUT_MS = 1200
BENCH_MAX_SPEED = 1.0
BENCH_MAX_TIMEOUT_MS = 10000
BENCH_MAX_DISTANCE_CM = 100.0
BENCH_MAX_DURATION_MS = 10000
DEFAULT_TURN_ANGLE_DEG = 30.0


MOTION_ALIASES = {
    "forward": "move_out_of_dock",
    "fwd": "move_out_of_dock",
    "back": "move_back_to_dock",
    "backward": "move_back_to_dock",
    "reverse": "move_back_to_dock",
    "left": "turn",
    "right": "turn",
}


def _arg_value(args: argparse.Namespace, *names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(args, name, None)
        if value is not None:
            return value
    return default


def _clamp_number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _clamp_motion_speed(value: Any, default: float, minimum: float, maximum: float) -> float:
    speed = _clamp_number(value, default, 0.0, maximum)
    if speed <= 0.0:
        return 0.0
    return max(minimum, speed)


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _motion_action(raw_action: Any) -> tuple[str, float | None]:
    action = str(raw_action or "move_out_of_dock")
    normalized = MOTION_ALIASES.get(action, action)
    if action == "left":
        return normalized, -DEFAULT_TURN_ANGLE_DEG
    if action == "right":
        return normalized, DEFAULT_TURN_ANGLE_DEG
    return normalized, None


def build_agent_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command_name == "expression":
        payload = {
            "command": "display.expression",
            "expression": _arg_value(
                args,
                "expression",
                "expression_opt",
                "expression_arg",
                default="caring",
            ),
            "duration_ms": int(_arg_value(args, "duration_ms", default=3000)),
            "loop": bool(_arg_value(args, "loop", default=False)),
        }
    elif args.command_name == "motion":
        bench = bool(getattr(args, "bench", False))
        max_speed = BENCH_MAX_SPEED if bench else MAX_SAFE_SPEED
        min_speed = 0.0 if bench else MIN_SAFE_SPEED
        max_timeout = BENCH_MAX_TIMEOUT_MS if bench else MAX_SAFE_TIMEOUT_MS
        max_distance = BENCH_MAX_DISTANCE_CM if bench else MAX_SAFE_DISTANCE_CM
        max_duration = BENCH_MAX_DURATION_MS if bench else MAX_SAFE_TIMEOUT_MS
        raw_action = _arg_value(args, "action", "action_opt", "action_arg", default="move_out_of_dock")
        action, default_param = _motion_action(raw_action)
        payload = {
            "command": "motion.execute",
            "action": action,
        }
        if bench:
            payload["bench"] = True
        params: dict[str, Any] = {}
        speed = _arg_value(args, "speed")
        distance_cm = _arg_value(args, "distance_cm")
        duration_ms = _arg_value(args, "duration_ms")
        angle_deg = _arg_value(args, "angle_deg")
        timeout_ms = _arg_value(args, "timeout_ms")
        if speed is not None:
            params["speed"] = _clamp_motion_speed(speed, max_speed, min_speed, max_speed)
        if distance_cm is not None:
            params["distance_cm"] = _clamp_number(
                distance_cm,
                max_distance,
                0.0,
                max_distance,
            )
        if duration_ms is not None:
            params["duration_ms"] = _clamp_int(duration_ms, max_duration, 1, max_duration)
        if action == "turn":
            turn_param = angle_deg if angle_deg is not None else default_param
            if turn_param is not None:
                params["angle_deg"] = _clamp_number(turn_param, 0.0, -360.0, 360.0)
        if params:
            payload["params"] = params
        if timeout_ms is not None:
            payload["timeout_ms"] = _clamp_int(timeout_ms, max_timeout, 1, max_timeout)
    elif args.command_name == "tts":
        payload = {
            "command": "audio.play_tts",
            "text": args.text,
        }
    elif args.command_name == "local":
        payload = {
            "command": "audio.play_local",
            "sound": _arg_value(args, "sound", "sound_opt", "sound_arg", default="care_01"),
            "volume": float(_arg_value(args, "volume", default=0.7)),
        }
    else:
        raise ValueError(f"Unsupported command: {args.command_name}")

    device_id = _arg_value(args, "device_id")
    if device_id:
        payload["device_id"] = device_id

    return {
        "type": "agent.command",
        "payload": payload,
    }


async def send_command(args: argparse.Namespace) -> None:
    try:
        import websockets
    except ImportError:
        print("Missing dependency: websockets. Install base_station/requirements.txt first.")
        sys.exit(2)

    message = build_agent_command(args)
    try:
        async with websockets.connect(args.url) as websocket:
            await websocket.send(json.dumps(message, ensure_ascii=False))
            raw_ack = await websocket.recv()
    except OSError as exc:
        print(f"Connection failed: could not reach {args.url}. Is the base station running? ({exc})")
        sys.exit(1)
    except websockets.exceptions.InvalidURI as exc:
        print(f"Connection failed: invalid WebSocket URI {args.url}. ({exc})")
        sys.exit(1)

    try:
        ack = json.loads(raw_ack)
    except json.JSONDecodeError:
        print(raw_ack)
        return

    print(json.dumps(ack, ensure_ascii=False, indent=2))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a local Agent command to Xiao An base_station.")
    parser.add_argument("--url", default=DEFAULT_AGENT_URL, help="Base station /agent WebSocket URL.")
    parser.add_argument("--device-id", default=None, help="Optional target robot device_id.")

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    expression = subparsers.add_parser("expression", help="Forward a display.expression command.")
    expression.add_argument("expression_arg", nargs="?", default=None, help="Expression name, for example caring.")
    expression.add_argument("--expression", dest="expression_opt", default=None, help="Expression name, for example caring.")
    expression.add_argument("--duration-ms", type=int, default=3000, help="Expression duration in milliseconds.")
    expression.add_argument("--loop", action="store_true", help="Ask the robot to loop the expression.")

    motion = subparsers.add_parser("motion", help="Forward a motion.execute command.")
    motion.add_argument("action_arg", nargs="?", default=None, help="Motion action name.")
    motion.add_argument("--action", dest="action_opt", default=None, help="Motion action name.")
    motion.add_argument("--speed", type=float, default=None, help="Motion speed from 0.0 to 1.0.")
    motion.add_argument("--distance-cm", type=float, default=None, help="Forward travel distance in centimeters.")
    motion.add_argument("--duration-ms", type=int, default=None, help="Open-loop motion duration in milliseconds.")
    motion.add_argument("--angle-deg", type=float, default=None, help="Turn angle for left/right/turn commands.")
    motion.add_argument("--timeout-ms", type=int, default=None, help="Motion timeout in milliseconds.")
    motion.add_argument(
        "--bench",
        action="store_true",
        help="Bench mode: allow speed up to 1.0 and timeout up to 10s (wheels lifted, external VM).",
    )

    tts = subparsers.add_parser("tts", help="Forward an audio.play_tts command.")
    tts.add_argument("--text", required=True, help="Text preview to send with the mock TTS command.")

    local = subparsers.add_parser("local", help="Forward an audio.play_local command.")
    local.add_argument("sound_arg", nargs="?", default=None, help="Local sound id, for example care_01.")
    local.add_argument("--sound", dest="sound_opt", default=None, help="Local sound id, for example care_01.")
    local.add_argument("--volume", type=float, default=0.7, help="Playback volume from 0.0 to 1.0.")

    return parser.parse_args(argv)


if __name__ == "__main__":
    asyncio.run(send_command(parse_args()))
