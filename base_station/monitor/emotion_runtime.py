"""Base station emotion monitoring runtime.

This is the formal base_station entry point for running an emotion source into
XiaoAnBrain. It currently supports fake sources used by the local MVP; real
camera/OpenVINO sources can replace them later without changing the event loop
contract.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
from typing import Any

from agent.core.brain import XiaoAnBrain
from base_station.monitor.emotion_event_loop import EmotionEventLoop
from base_station.perception.face_emotion_pipeline import CameraEmotionSource, FaceEmotionPipeline
from base_station.perception.fake_camera import FakeCameraFrameSource
from base_station.perception.fake_face_emotion import FakeFaceEmotionSource


class BaseStationEmotionRuntime:
    """Run an emotion source through EmotionEventLoop into the Agent brain."""

    def __init__(self, source: Any, event_loop: EmotionEventLoop, verbose: bool = True):
        self.source = source
        self.event_loop = event_loop
        self.verbose = verbose

    async def run(self) -> list[dict]:
        results = []
        async for sample in self.source.samples():
            result = await self.event_loop.handle_sample(sample)
            results.append(result)
            if self.verbose:
                print(json.dumps({
                    "sample": sample,
                    "result": result,
                }, ensure_ascii=False, indent=2))
        return results


@contextmanager
def runtime_db_path(db_path: str, fresh_db: bool):
    if fresh_db:
        with tempfile.TemporaryDirectory(prefix="xiao_an_emotion_runtime_") as temp_dir:
            yield str(Path(temp_dir) / "xiao_an_runtime.db")
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    yield db_path


def create_emotion_source(
    source: str,
    pattern: str,
    count: int | None,
    interval_seconds: float,
):
    if source == "fake_face":
        return FakeFaceEmotionSource(
            pattern=pattern,
            count=count,
            interval_seconds=interval_seconds,
        )

    if source == "fake_camera":
        frame_source = FakeCameraFrameSource(
            count=count,
            interval_seconds=interval_seconds,
        )
        pipeline = FaceEmotionPipeline(pattern=pattern)
        return CameraEmotionSource(frame_source=frame_source, pipeline=pipeline)

    raise ValueError(
        f"Unsupported emotion source: {source}. Currently supported sources: fake_face, fake_camera."
    )


def create_runtime(
    source_name: str = "fake_face",
    pattern: str = "tired",
    count: int | None = 5,
    interval_seconds: float = 1.0,
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: str = "agent/data/xiao_an.db",
    verbose: bool = True,
) -> BaseStationEmotionRuntime:
    gateway_url = f"ws://{host}:{port}/agent"
    brain = XiaoAnBrain(
        gateway_url=gateway_url,
        db_path=db_path,
    )
    source = create_emotion_source(
        source=source_name,
        pattern=pattern,
        count=count,
        interval_seconds=interval_seconds,
    )
    event_loop = EmotionEventLoop(brain=brain)
    return BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=verbose)


def create_fake_face_runtime(
    pattern: str = "tired",
    count: int | None = 5,
    interval_seconds: float = 1.0,
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: str = "agent/data/xiao_an.db",
    verbose: bool = True,
) -> BaseStationEmotionRuntime:
    return create_runtime(
        source_name="fake_face",
        pattern=pattern,
        count=count,
        interval_seconds=interval_seconds,
        host=host,
        port=port,
        db_path=db_path,
        verbose=verbose,
    )


def parse_count(value: str) -> int | None:
    if value.lower() in {"none", "null", "infinite"}:
        return None
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--count must be non-negative or None")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Xiao An base station emotion monitoring runtime.")
    parser.add_argument(
        "--source",
        default="fake_face",
        choices=["fake_face", "fake_camera"],
        help="Emotion source.",
    )
    parser.add_argument(
        "--pattern",
        choices=["neutral", "tired", "anxious", "mixed"],
        default="tired",
        help="Fake face pattern.",
    )
    parser.add_argument("--count", type=parse_count, default=5, help="Number of samples, or None for infinite.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between samples.")
    parser.add_argument("--host", default="127.0.0.1", help="Base station host.")
    parser.add_argument("--port", type=int, default=8765, help="Base station /agent port.")
    parser.add_argument("--db-path", default="agent/data/xiao_an.db", help="SQLite database path.")
    parser.add_argument("--fresh-db", action="store_true", help="Use a fresh temporary SQLite database for this run.")
    parser.add_argument("--verbose", action="store_true", help="Print each sample and result.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    with runtime_db_path(args.db_path, args.fresh_db) as active_db_path:
        runtime = create_runtime(
            source_name=args.source,
            pattern=args.pattern,
            count=args.count,
            interval_seconds=args.interval,
            host=args.host,
            port=args.port,
            db_path=active_db_path,
            verbose=args.verbose,
        )
        try:
            await runtime.run()
        finally:
            runtime.event_loop.brain.close()


if __name__ == "__main__":
    asyncio.run(main())
