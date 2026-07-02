"""Simulate a local emotion stream and feed it into XiaoAnBrain."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile

from agent.core.brain import XiaoAnBrain
from base_station.monitor.emotion_event_loop import EmotionEventLoop
from base_station.perception.fake_face_emotion import FakeFaceEmotionSource


def build_sample(pattern: str, index: int) -> dict:
    sample = FakeFaceEmotionSource(pattern=pattern, count=0, interval_seconds=0).build_sample(index)
    sample["seq"] = index + 1
    return sample


def generate_samples(pattern: str, count: int) -> list[dict]:
    return [build_sample(pattern, index) for index in range(count)]


@contextmanager
def simulation_db_path(db_path: str, fresh_db: bool):
    if fresh_db:
        with tempfile.TemporaryDirectory(prefix="xiao_an_emotion_stream_") as temp_dir:
            yield str(Path(temp_dir) / "xiao_an_simulation.db")
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    yield db_path


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
    parser.add_argument(
        "--fresh-db",
        action="store_true",
        help="Use a fresh temporary SQLite database for this run.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    url = f"ws://{args.host}:{args.port}/agent"
    with simulation_db_path(args.db_path, args.fresh_db) as active_db_path:
        brain = XiaoAnBrain(
            gateway_url=url,
            db_path=active_db_path,
        )
        event_loop = EmotionEventLoop(brain=brain)
        emotion_source = FakeFaceEmotionSource(
            pattern=args.pattern,
            count=args.count,
            interval_seconds=args.interval,
        )

        try:
            index = 0
            async for sample in emotion_source.samples():
                sample["seq"] = index + 1
                result = await event_loop.handle_sample(sample)
                print(json.dumps({
                    "sample": sample,
                    "result": result,
                }, ensure_ascii=False, indent=2))
                index += 1
        finally:
            brain.close()


if __name__ == "__main__":
    asyncio.run(main())
