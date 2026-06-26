"""Send one simulated frontend message event to XiaoAnBrain."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.core.brain import XiaoAnBrain


def build_frontend_event(text: str, session_id: str = "default") -> dict:
    return {
        "type": "frontend.message",
        "payload": {
            "text": text,
            "session_id": session_id,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one simulated frontend message to XiaoAnBrain.")
    parser.add_argument("message", nargs="?", help="Frontend message text.")
    parser.add_argument("--text", help="Frontend message text.")
    parser.add_argument("--session-id", default="default", help="Frontend session id.")
    parser.add_argument("--verbose", action="store_true", help="Accepted for local debugging; output is always JSON.")
    args = parser.parse_args()
    args.text = args.text or args.message
    if not args.text:
        parser.error("message text is required")
    return args


async def main() -> None:
    args = parse_args()
    brain = XiaoAnBrain()
    try:
        result = await brain.handle_event(build_frontend_event(args.text, args.session_id))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        brain.close()


if __name__ == "__main__":
    asyncio.run(main())
