"""Simulate a local emotion stream and feed it into XiaoAnBrain."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from base_station.monitor.emotion_event_loop import EmotionEventLoop


SAMPLE_PATTERNS = {
    "neutral": {
        "source": "face",
        "emotion_tag": "neutral",
        "confidence": 0.5,
        "fatigue_score": 0.2,
    },
    "tired": {
        "source": "face",
        "emotion_tag": "tired",
        "confidence": 0.9,
        "fatigue_score": 0.85,
    },
    "anxious": {
        "source": "face",
        "emotion_tag": "anxious",
        "confidence": 0.88,
        "fatigue_score": 0.4,
    },
}

MIXED_PATTERN = ["neutral", "tired", "tired", "neutral", "anxious"]


def build_sample(pattern: str, index: int) -> dict:
    if pattern == "mixed":
        pattern = MIXED_PATTERN[index % len(MIXED_PATTERN)]

    sample = SAMPLE_PATTERNS[pattern].copy()
    sample["seq"] = index + 1
    return sample


def generate_samples(pattern: str, count: int) -> list[dict]:
    return [build_sample(pattern, index) for index in range(count)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate emotion samples for XiaoAnBrain.")
    parser.add_argument(
        "--pattern",
        choices=["neutral", "tired", "anxious", "mixed"],
        default="tired",
        help="Sample pattern to generate.",
    )
    parser.add_argument("--count", type=int, default=5, help="Number of samples to generate.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between samples.")
    parser.add_argument("--host", default="127.0.0.1", help="Base station host.")
    parser.add_argument("--port", type=int, default=8765, help="Base station /agent port.")
    parser.add_argument("--db-path", default="agent/data/xiao_an.db", help="SQLite database path.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    Path(args.db_path).parent.mkdir(parents=True, exist_ok=True)
    url = f"ws://{args.host}:{args.port}/agent"
    brain = XiaoAnBrain(
        gateway_url=url,
        db_path=args.db_path,
    )
    event_loop = EmotionEventLoop(brain=brain)

    try:
        for sample in generate_samples(args.pattern, args.count):
            result = await event_loop.handle_sample(sample)
            print(json.dumps({
                "sample": sample,
                "result": result,
            }, ensure_ascii=False, indent=2))
            if args.interval > 0:
                await asyncio.sleep(args.interval)
    finally:
        brain.close()


if __name__ == "__main__":
    asyncio.run(main())
