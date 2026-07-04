"""Run the OpenClaw P0 robot capability preflight.

The runner uses only the base-station /agent channel. It sends the same robot
commands OpenClaw will use, then polls /agent state/events to verify robot-side
acks and completion signals.
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

PHRASES = {
    "hello_intro": "你好，我是小安。",
    "ack_help": "好的，我来帮你。",
    "repeat": "请你再说一次。",
}


def format_console_json(data: dict[str, Any]) -> str:
    """Return JSON that can be printed on non-UTF-8 Windows consoles."""

    return json.dumps(data, ensure_ascii=True, indent=2)


@dataclass(frozen=True)
class EventCheck:
    event_type: str
    command_type: str | None = None
    status: str | None = None
    require_bytes_written: bool = False


@dataclass(frozen=True)
class P0Step:
    step_id: str
    capability: str
    payload: dict[str, Any] | None
    checks: tuple[EventCheck, ...]
    physical_result: str
    timeout_sec: float = 10.0


def _with_device(payload: dict[str, Any], device_id: str | None) -> dict[str, Any]:
    command_payload = dict(payload)
    if device_id:
        command_payload["device_id"] = device_id
    return command_payload


def build_p0_steps(device_id: str | None = DEFAULT_DEVICE_ID) -> list[P0Step]:
    return [
        P0Step(
            step_id="P0-1",
            capability="Robot online",
            payload=None,
            checks=(),
            physical_result="ESP is connected to the base-station hotspot and heartbeats continue.",
        ),
        P0Step(
            step_id="P0-2",
            capability="Spoken TTS intro",
            payload=_with_device({"command": "audio.play_tts", "text": PHRASES["hello_intro"]}, device_id),
            checks=(
                EventCheck("command.ack", "audio.play_tts", "accepted"),
                EventCheck("audio.playback_done", "audio.play_tts", "ok", require_bytes_written=True),
            ),
            physical_result='Xiao-An says "ni hao, wo shi xiao an" clearly enough.',
            timeout_sec=25.0,
        ),
        P0Step(
            step_id="P0-3",
            capability="Spoken TTS arbitrary sentence",
            payload=_with_device({"command": "audio.play_tts", "text": PHRASES["ack_help"]}, device_id),
            checks=(
                EventCheck("command.ack", "audio.play_tts", "accepted"),
                EventCheck("audio.playback_done", "audio.play_tts", "ok", require_bytes_written=True),
            ),
            physical_result="Robot speaks a different sentence, proving this is not fixed audio.",
            timeout_sec=25.0,
        ),
        P0Step(
            step_id="P0-4",
            capability="Spoken TTS fallback phrase",
            payload=_with_device({"command": "audio.play_tts", "text": PHRASES["repeat"]}, device_id),
            checks=(
                EventCheck("command.ack", "audio.play_tts", "accepted"),
                EventCheck("audio.playback_done", "audio.play_tts", "ok", require_bytes_written=True),
            ),
            physical_result="Robot says a short fallback phrase.",
            timeout_sec=25.0,
        ),
        P0Step(
            step_id="P0-5",
            capability="Local wake sound",
            payload=_with_device({"command": "audio.play_local", "sound": "wake_01", "volume": 0.7}, device_id),
            checks=(EventCheck("command.ack", "audio.play_local", "ok"),),
            physical_result="Wake chime is audible.",
        ),
        P0Step(
            step_id="P0-6",
            capability="Face thinking",
            payload=_with_device({
                "command": "display.expression",
                "expression": "thinking",
                "duration_ms": 1500,
            }, device_id),
            checks=(EventCheck("command.ack", "display.expression", "ok"),),
            physical_result="Face changes to thinking.",
        ),
        P0Step(
            step_id="P0-7",
            capability="Face speaking",
            payload=_with_device({
                "command": "display.expression",
                "expression": "speaking",
                "duration_ms": 1500,
            }, device_id),
            checks=(EventCheck("command.ack", "display.expression", "ok"),),
            physical_result="Face changes to speaking.",
        ),
        P0Step(
            step_id="P0-8",
            capability="Stop motion",
            payload=_with_device({
                "command": "motion.execute",
                "action": "stop",
                "timeout_ms": 500,
            }, device_id),
            checks=(EventCheck("command.ack", "motion.execute", "ok"),),
            physical_result="Robot stops or remains still, with no unexpected movement.",
        ),
    ]


async def _agent_request(url: str, message: dict[str, Any], timeout_sec: float) -> dict[str, Any]:
    try:
        import websockets
    except ImportError:
        raise RuntimeError("Missing dependency: websockets. Install base_station requirements first.") from None

    async with websockets.connect(url, open_timeout=min(timeout_sec, 4.0)) as websocket:
        await websocket.send(json.dumps(message, ensure_ascii=False))
        raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_sec)
    return json.loads(raw)


async def query_state(url: str, timeout_sec: float = 5.0) -> dict[str, Any]:
    return await _agent_request(
        url,
        {"type": "agent.query", "payload": {"query": "state"}},
        timeout_sec,
    )


async def query_events(
    url: str,
    *,
    since: float,
    device_id: str | None,
    event_type: str | None = None,
    timeout_sec: float = 5.0,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"query": "recent_events", "since": since}
    if device_id:
        payload["device_id"] = device_id
    if event_type:
        payload["event_type"] = event_type
    response = await _agent_request(url, {"type": "agent.query", "payload": payload}, timeout_sec)
    if response.get("type") != "agent.events":
        raise RuntimeError(f"Unexpected event query response: {response}")
    return list(response.get("payload", {}).get("events", []))


async def send_command(url: str, payload: dict[str, Any], timeout_sec: float) -> dict[str, Any]:
    response = await _agent_request(
        url,
        {"type": "agent.command", "payload": payload},
        timeout_sec,
    )
    if response.get("type") != "agent.ack":
        raise RuntimeError(f"Unexpected command response: {response}")
    return response


def _event_matches(event: dict[str, Any], check: EventCheck) -> bool:
    if event.get("type") != check.event_type:
        return False
    payload = event.get("payload", {})
    if check.command_type and payload.get("command_type") != check.command_type:
        return False
    if check.status and payload.get("status") != check.status:
        return False
    if check.require_bytes_written:
        try:
            return int(payload.get("bytes_written", 0)) > 0
        except (TypeError, ValueError):
            return False
    return True


async def wait_for_event(
    url: str,
    *,
    since: float,
    device_id: str | None,
    check: EventCheck,
    timeout_sec: float,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while True:
        events = await query_events(
            url,
            since=since,
            device_id=device_id,
            event_type=check.event_type,
            timeout_sec=5.0,
        )
        for event in events:
            if _event_matches(event, check):
                return event
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {check}")
        await asyncio.sleep(0.35)


def _find_session(state: dict[str, Any], device_id: str | None) -> dict[str, Any] | None:
    sessions = state.get("payload", {}).get("sessions", [])
    if not device_id:
        return sessions[0] if sessions else None
    for session in sessions:
        if session.get("device_id") == device_id:
            return session
    return None


async def run(args: argparse.Namespace) -> int:
    steps = build_p0_steps(args.device_id)
    print("OpenClaw P0 preflight")
    print(f"url={args.url} device_id={args.device_id or '<auto>'} dry_run={args.dry_run}")
    print("Keep robot motion physically blocked or lifted; P0-8 is stop-only.")

    for step in steps:
        print(f"\n{step.step_id} {step.capability}")
        print(f"physical: {step.physical_result}")
        if step.payload:
            print(format_console_json({"type": "agent.command", "payload": step.payload}))

        if args.dry_run:
            continue

        state = await query_state(args.url)
        session = _find_session(state, args.device_id)
        if session is None:
            print(f"FAIL {step.step_id}: robot is not online", file=sys.stderr)
            return 1
        if session.get("last_heartbeat_age_sec", 999) > args.max_heartbeat_age_sec:
            print(f"FAIL {step.step_id}: heartbeat stale: {session}", file=sys.stderr)
            return 1

        since = float(state.get("payload", {}).get("server_time", 0.0))
        if step.payload is None:
            print(f"PASS {step.step_id}: online session {session.get('device_id')} age={session.get('last_heartbeat_age_sec'):.1f}s")
            continue

        ack = await send_command(args.url, step.payload, step.timeout_sec)
        if not ack.get("payload", {}).get("ok"):
            print(f"FAIL {step.step_id}: agent ack failed: {ack}", file=sys.stderr)
            return 1
        print(f"agent ack: {ack.get('payload')}")

        for check in step.checks:
            event = await wait_for_event(
                args.url,
                since=since,
                device_id=args.device_id,
                check=check,
                timeout_sec=step.timeout_sec,
            )
            print(f"event ok: {event['type']} {event.get('payload')}")

        await asyncio.sleep(args.step_delay_sec)
        print(f"PASS {step.step_id}")

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenClaw P0 preflight checks through /agent.")
    parser.add_argument("--url", default=DEFAULT_AGENT_URL, help="Base-station /agent WebSocket URL.")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help="Target robot device id; pass empty for auto.")
    parser.add_argument("--max-heartbeat-age-sec", type=float, default=20.0, help="Maximum acceptable heartbeat age.")
    parser.add_argument("--step-delay-sec", type=float, default=0.4, help="Delay after each passed step.")
    parser.add_argument("--dry-run", action="store_true", help="Print P0 commands without sending them.")
    args = parser.parse_args(argv)
    if args.device_id == "":
        args.device_id = None
    return args


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
