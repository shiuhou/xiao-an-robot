"""Run the Xiao-An spoken TTS bottom-capability demo sequence.

The runner talks to the base-station /agent WebSocket, which forwards each
command to the robot over /control. It is intentionally small and explicit so
the hardware operator can see which physical effect should happen at each step.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any


DEFAULT_AGENT_URL = "ws://127.0.0.1:8765/agent"
DEFAULT_DEVICE_ID = "xiaoan_robot_01"


@dataclass(frozen=True)
class DemoStep:
    name: str
    payload: dict[str, Any]
    expected: str
    wait_seconds: float = 1.0


def agent_message(payload: dict[str, Any], device_id: str | None) -> dict[str, Any]:
    command_payload = dict(payload)
    if device_id:
        command_payload["device_id"] = device_id
    return {
        "type": "agent.command",
        "payload": command_payload,
    }


def expression_step(name: str, expression: str, expected: str, duration_ms: int = 1400) -> DemoStep:
    return DemoStep(
        name=name,
        payload={
            "command": "display.expression",
            "expression": expression,
            "duration_ms": duration_ms,
        },
        expected=expected,
        wait_seconds=max(0.4, duration_ms / 1000.0),
    )


def local_audio_step(name: str, sound: str, expected: str, wait_seconds: float = 1.2) -> DemoStep:
    return DemoStep(
        name=name,
        payload={
            "command": "audio.play_local",
            "sound": sound,
            "volume": 0.7,
        },
        expected=expected,
        wait_seconds=wait_seconds,
    )


def spoken_tts_step(text: str) -> DemoStep:
    return DemoStep(
        name="spoken_tts",
        payload={
            "command": "audio.play_tts",
            "text": text,
            "duration_ms": max(1200, len(text) * 180),
        },
        expected="Robot should speak the requested text via streamed TTS, or the embedded phrase when streaming is disabled.",
        wait_seconds=2.4,
    )


def motion_step(
    name: str,
    action: str,
    expected: str,
    *,
    bench: bool,
    speed: float,
    duration_ms: int,
    timeout_ms: int,
    angle_deg: float | None = None,
) -> DemoStep:
    params: dict[str, Any] = {
        "speed": speed,
        "duration_ms": duration_ms,
    }
    if angle_deg is not None:
        params["angle_deg"] = angle_deg
    payload: dict[str, Any] = {
        "command": "motion.execute",
        "action": action,
        "params": params,
        "timeout_ms": timeout_ms,
    }
    if bench:
        payload["bench"] = True
    return DemoStep(
        name=name,
        payload=payload,
        expected=expected,
        wait_seconds=max(1.0, timeout_ms / 1000.0 + 0.4),
    )


def build_steps(args: argparse.Namespace) -> list[DemoStep]:
    steps = [
        expression_step("face_thinking", "thinking", "Face should switch to thinking/listening posture."),
        local_audio_step("wake_chime", "wake_01", "Speaker should play the wake/success chime."),
        expression_step("face_speaking", "speaking", "Face should switch to speaking."),
        spoken_tts_step(args.tts_text),
        expression_step("face_caring", "caring", "Face should switch to caring."),
        local_audio_step("care_chime", "care_01", "Speaker should play the care chime."),
    ]

    if args.include_motion:
        steps.extend(
            [
                motion_step(
                    "move_forward",
                    "move_out_of_dock",
                    "Robot should move forward briefly; server should log motion.completed.",
                    bench=args.bench_motion,
                    speed=args.motion_speed,
                    duration_ms=args.forward_ms,
                    timeout_ms=args.forward_timeout_ms,
                ),
                motion_step(
                    "turn_left",
                    "turn",
                    "Robot should turn left briefly; server should log motion.completed.",
                    bench=args.bench_motion,
                    speed=args.motion_speed,
                    duration_ms=args.turn_ms,
                    timeout_ms=args.turn_timeout_ms,
                    angle_deg=-25.0,
                ),
            ]
        )

    steps.extend(
        [
            expression_step("face_happy", "happy", "Face should switch to happy."),
            local_audio_step("success_ding", "success_ding", "Speaker should play the success ding."),
        ]
    )
    return steps


async def send_step(args: argparse.Namespace, step: DemoStep, index: int, total: int) -> bool:
    message = agent_message(step.payload, args.device_id)
    print(f"\n[{index}/{total}] {step.name}")
    print(f"expected: {step.expected}")
    if args.dry_run:
        print(json.dumps(message, ensure_ascii=False, indent=2))
        return True

    try:
        import websockets
    except ImportError:
        print("Missing dependency: websockets. Install requirements.txt first.", file=sys.stderr)
        return False

    try:
        async with websockets.connect(args.url, open_timeout=args.connect_timeout) as websocket:
            await websocket.send(json.dumps(message, ensure_ascii=False))
            raw_ack = await asyncio.wait_for(websocket.recv(), timeout=args.ack_timeout)
    except Exception as exc:
        print(f"send failed: {exc}", file=sys.stderr)
        return False

    try:
        ack = json.loads(raw_ack)
    except json.JSONDecodeError:
        print(f"raw ack: {raw_ack}")
        return False

    print(json.dumps(ack, ensure_ascii=False, indent=2))
    ok = bool(ack.get("payload", {}).get("ok"))
    if not ok:
        return False
    await asyncio.sleep(step.wait_seconds * args.wait_scale)
    return True


async def run(args: argparse.Namespace) -> int:
    steps = build_steps(args)
    print("Xiao-An spoken TTS demo runner")
    print(f"url={args.url} device_id={args.device_id or '<auto>'} steps={len(steps)} dry_run={args.dry_run}")
    if args.include_motion:
        print("motion=enabled; keep the robot clear of people, cables, and table edges.")
    else:
        print("motion=disabled; pass --include-motion only when the robot is physically safe to move.")

    for index, step in enumerate(steps, start=1):
        ok = await send_step(args, step, index, len(steps))
        if not ok and not args.continue_on_error:
            print(f"stopped at step: {step.name}", file=sys.stderr)
            return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Xiao-An spoken TTS demo sequence.")
    parser.add_argument("--url", default=DEFAULT_AGENT_URL, help="Base-station /agent WebSocket URL.")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help="Target robot device_id; use empty string for auto.")
    parser.add_argument("--tts-text", default="I can speak now.", help="Text preview sent with audio.play_tts.")
    parser.add_argument("--include-motion", action="store_true", help="Include short safe motion steps.")
    parser.add_argument("--bench-motion", action="store_true", help="Mark motion commands as bench mode for lifted-wheel tests.")
    parser.add_argument("--motion-speed", type=float, default=1.0, help="Motion speed used by the demo.")
    parser.add_argument("--forward-ms", type=int, default=800, help="Forward motion duration.")
    parser.add_argument("--forward-timeout-ms", type=int, default=1200, help="Forward motion timeout.")
    parser.add_argument("--turn-ms", type=int, default=450, help="Turn motion duration.")
    parser.add_argument("--turn-timeout-ms", type=int, default=900, help="Turn motion timeout.")
    parser.add_argument("--wait-scale", type=float, default=1.0, help="Scale delays between steps.")
    parser.add_argument("--connect-timeout", type=float, default=4.0, help="WebSocket connect timeout.")
    parser.add_argument("--ack-timeout", type=float, default=6.0, help="Agent ack timeout.")
    parser.add_argument("--dry-run", action="store_true", help="Print messages without connecting.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue even if a step fails.")
    args = parser.parse_args(argv)
    if args.device_id == "":
        args.device_id = None
    return args


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
