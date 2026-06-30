"""Manually test XiaoAnBrain with an emotion event."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agent.core.brain import XiaoAnBrain


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one emotion event to XiaoAnBrain.")
    parser.add_argument("--db", default="agent/data/xiao_an.db", help="SQLite database path.")
    parser.add_argument("--url", default="ws://127.0.0.1:8765/agent", help="Base station /agent WebSocket URL.")
    parser.add_argument("--source", choices=["face", "voice"], default="face", help="Emotion source.")
    parser.add_argument("--emotion", default="neutral", help="Emotion tag.")
    parser.add_argument("--confidence", type=float, default=0.8, help="Emotion confidence score.")
    parser.add_argument("--fatigue", type=float, default=0.0, help="Fatigue score.")
    parser.add_argument("--type", default="emotion.sample", help="Event type.")
    parser.add_argument("--window-seconds", type=int, default=300, help="Sliding window size in seconds.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    brain = XiaoAnBrain(
        gateway_url=args.url,
        db_path=args.db,
        window_seconds=args.window_seconds,
    )
    try:
        result = await brain.handle_event({
            "type": args.type,
            "payload": {
                "source": args.source,
                "emotion_tag": args.emotion,
                "confidence": args.confidence,
                "fatigue_score": args.fatigue,
            },
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        brain.close()


if __name__ == "__main__":
    asyncio.run(main())
