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


def build_agent_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command_name == "expression":
        payload = {
            "command": "display.expression",
            "expression": args.expression,
        }
    elif args.command_name == "motion":
        payload = {
            "command": "motion.execute",
            "action": args.action,
        }
    elif args.command_name == "tts":
        payload = {
            "command": "audio.play_tts",
            "text": args.text,
        }
    elif args.command_name == "local":
        payload = {
            "command": "audio.play_local",
            "sound": args.sound,
        }
    else:
        raise ValueError(f"Unsupported command: {args.command_name}")

    if args.device_id:
        payload["device_id"] = args.device_id

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a local Agent command to Xiao An base_station.")
    parser.add_argument("--url", default=DEFAULT_AGENT_URL, help="Base station /agent WebSocket URL.")
    parser.add_argument("--device-id", default=None, help="Optional target robot device_id.")

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    expression = subparsers.add_parser("expression", help="Forward a display.expression command.")
    expression.add_argument("--expression", default="caring", help="Expression name, for example caring.")

    motion = subparsers.add_parser("motion", help="Forward a motion.execute command.")
    motion.add_argument("--action", default="move_out_of_dock", help="Motion action name.")

    tts = subparsers.add_parser("tts", help="Forward an audio.play_tts command.")
    tts.add_argument("--text", required=True, help="Text preview to send with the mock TTS command.")

    local = subparsers.add_parser("local", help="Forward an audio.play_local command.")
    local.add_argument("--sound", default="care_01", help="Local sound id, for example care_01.")

    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(send_command(parse_args()))
