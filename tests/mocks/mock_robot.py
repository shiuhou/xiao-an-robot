"""Simple fake robot for DK2500 WebSocket /control testing.

Run this when the real ESP32 firmware is not connected. The mock sends the same
basic lifecycle messages a robot should send and prints commands from the base
station so developers can verify the control channel by eye.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any


COMMAND_TYPES = {
    "motion.execute",
    "display.expression",
    "audio.play_tts",
    "audio.play_local",
    "config.update",
    "system.shutdown",
}


def log(message: str) -> None:
    print(message, flush=True)


class Sequence:
    """Small counter for readable, increasing message sequence numbers."""

    def __init__(self) -> None:
        self.value = 0

    def next(self) -> int:
        self.value += 1
        return self.value


def now_ms() -> int:
    return int(time.time() * 1000)


def build_message(seq: Sequence, msg_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": msg_type,
        "ts": now_ms(),
        "seq": seq.next(),
        "payload": payload,
    }


async def send_heartbeats(websocket: Any, seq: Sequence, device_id: str, interval_sec: int) -> None:
    """Send periodic heartbeat messages until the WebSocket closes."""

    battery = 96
    while True:
        await asyncio.sleep(interval_sec)
        battery = max(0, battery - 1)
        message = build_message(
            seq,
            "device.heartbeat",
            {
                "device_id": device_id,
                "battery": battery,
                "dock_status": "undocked",
                "uptime_sec": int(time.monotonic()),
            },
        )
        await websocket.send(json.dumps(message, ensure_ascii=False))
        log(f"> device.heartbeat battery={battery}%")


async def run_mock(args: argparse.Namespace) -> None:
    try:
        import websockets
    except ImportError:  # pragma: no cover - friendly CLI error path
        log("Missing dependency: websockets. Install base_station or agent requirements first.")
        sys.exit(2)

    seq = Sequence()
    uri = f"ws://{args.host}:{args.port}/control"

    try:
        async with websockets.connect(uri) as websocket:
            log(f"Connected to {uri}")
            hello = build_message(
                seq,
                "device.hello",
                {
                    "device_id": args.device_id,
                    "firmware": "mock-robot/0.1",
                    "battery": args.battery,
                    "capabilities": ["display", "motion", "tts"],
                },
            )
            await websocket.send(json.dumps(hello, ensure_ascii=False))
            log("> device.hello")

            heartbeat_task = asyncio.create_task(
                send_heartbeats(websocket, seq, args.device_id, args.heartbeat_interval)
            )
            try:
                async for raw in websocket:
                    try:
                        message = json.loads(raw)
                    except json.JSONDecodeError:
                        log(f"< non-json message: {raw!r}")
                        continue

                    msg_type = message.get("type", "<missing type>")
                    payload = message.get("payload", {})
                    if msg_type in COMMAND_TYPES:
                        log(f"< {msg_type}: {json.dumps(payload, ensure_ascii=False)}")
                    else:
                        log(f"< {msg_type}: {json.dumps(payload, ensure_ascii=False)}")
            finally:
                heartbeat_task.cancel()
    except OSError as exc:
        log(f"Connection failed: could not reach {uri}. Check host, port, and base station server. ({exc})")
        sys.exit(1)
    except websockets.exceptions.InvalidURI as exc:
        log(f"Connection failed: invalid WebSocket URI {uri}. ({exc})")
        sys.exit(1)
    except websockets.exceptions.ConnectionClosedError as exc:
        log(f"Connection closed by server: {exc}")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a fake Xiao An robot over WebSocket /control.")
    parser.add_argument("--host", default="127.0.0.1", help="Base station host, for example 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8765, help="Base station control WebSocket port.")
    parser.add_argument("--device-id", default="mock-robot-001", help="Device id reported in device.hello.")
    parser.add_argument("--battery", type=int, default=96, help="Initial fake battery percentage.")
    parser.add_argument("--heartbeat-interval", type=int, default=5, help="Seconds between heartbeats.")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run_mock(parse_args()))
