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
import sys
import tempfile
from typing import Any

from agent.core.brain import XiaoAnBrain
from base_station.monitor.emotion_event_loop import EmotionEventLoop
from base_station.perception.face_emotion_model import MockFaceEmotionModel
from base_station.perception.face_emotion_pipeline import CameraEmotionSource, FaceEmotionPipeline
from base_station.perception.fake_camera import FakeCameraFrameSource
from base_station.perception.fake_face_emotion import FakeFaceEmotionSource
from base_station.perception.opencv_camera import OpenCVCameraFrameSource
from base_station.perception.openvino_face_emotion_model import OpenVINOFaceEmotionModel
from base_station.perception.qwen_vl_emotion_model import FakeQwenVLEmotionModel


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


class LimitedEmotionSource:
    """Limit another emotion source to a finite number of samples."""

    def __init__(self, source: Any, count: int | None):
        self.source = source
        self.count = count

    async def samples(self):
        iterator = self.source.samples().__aiter__()
        emitted = 0
        try:
            while self.count is None or emitted < self.count:
                sample = await iterator.__anext__()
                emitted += 1
                yield sample
        finally:
            close = getattr(iterator, "aclose", None)
            if close is not None:
                await close()
            nested_source = self.source
            while nested_source is not None:
                frame_source = getattr(nested_source, "frame_source", None)
                frame_source_close = getattr(frame_source, "close", None)
                if frame_source_close is not None:
                    frame_source_close()
                    break
                nested_source = getattr(nested_source, "source", None)


class IntervalEmotionSource:
    """Add a delay after each emitted sample."""

    def __init__(self, source: Any, interval_seconds: float):
        self.source = source
        self.interval_seconds = interval_seconds

    async def samples(self):
        async for sample in self.source.samples():
            yield sample
            if self.interval_seconds > 0:
                await asyncio.sleep(self.interval_seconds)


class DirectModelEmotionPipeline:
    """Use a model that already returns a complete emotion sample."""

    def __init__(self, model: Any):
        self.model = model

    def process_frame(self, frame: dict) -> dict:
        return self.model.predict(frame).copy()


@contextmanager
def runtime_db_path(db_path: str, fresh_db: bool):
    if fresh_db:
        with tempfile.TemporaryDirectory(prefix="xiao_an_emotion_runtime_") as temp_dir:
            yield str(Path(temp_dir) / "xiao_an_runtime.db")
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    yield db_path


def create_face_emotion_model(
    model_backend: str,
    pattern: str,
    model_path: str | None = None,
    device: str = "CPU",
):
    if model_backend == "mock":
        return MockFaceEmotionModel(pattern=pattern)

    if model_backend == "openvino":
        if not model_path:
            raise ValueError("--model-path is required when --model-backend openvino")
        return OpenVINOFaceEmotionModel(model_path=model_path, device=device)

    if model_backend == "qwen_vl":
        return FakeQwenVLEmotionModel(pattern=pattern)

    raise ValueError(
        f"Unsupported model backend: {model_backend}. Currently supported backends: mock, openvino, qwen_vl."
    )


def create_emotion_pipeline(model_backend: str, model: Any, pattern: str):
    if model_backend == "qwen_vl":
        return DirectModelEmotionPipeline(model=model)
    return FaceEmotionPipeline(pattern=pattern, model=model)


def create_emotion_source(
    source: str,
    pattern: str,
    count: int | None,
    interval_seconds: float,
    camera_index: int = 0,
    camera_width: int | None = None,
    camera_height: int | None = None,
    model_backend: str = "mock",
    model_path: str | None = None,
    device: str = "CPU",
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
        model = create_face_emotion_model(
            model_backend=model_backend,
            pattern=pattern,
            model_path=model_path,
            device=device,
        )
        pipeline = create_emotion_pipeline(model_backend=model_backend, model=model, pattern=pattern)
        return CameraEmotionSource(frame_source=frame_source, pipeline=pipeline)

    if source == "opencv_camera":
        frame_source = OpenCVCameraFrameSource(
            camera_index=camera_index,
            width=camera_width,
            height=camera_height,
        )
        model = create_face_emotion_model(
            model_backend=model_backend,
            pattern=pattern,
            model_path=model_path,
            device=device,
        )
        pipeline = create_emotion_pipeline(model_backend=model_backend, model=model, pattern=pattern)
        camera_source = CameraEmotionSource(frame_source=frame_source, pipeline=pipeline)
        interval_source = IntervalEmotionSource(source=camera_source, interval_seconds=interval_seconds)
        return LimitedEmotionSource(source=interval_source, count=count)

    raise ValueError(
        "Unsupported emotion source: "
        f"{source}. Currently supported sources: fake_face, fake_camera, opencv_camera."
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
    camera_index: int = 0,
    camera_width: int | None = None,
    camera_height: int | None = None,
    model_backend: str = "mock",
    model_path: str | None = None,
    device: str = "CPU",
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
        camera_index=camera_index,
        camera_width=camera_width,
        camera_height=camera_height,
        model_backend=model_backend,
        model_path=model_path,
        device=device,
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


EXPECTED_CLI_ERRORS = (ValueError, ImportError, FileNotFoundError, RuntimeError)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Xiao An base station emotion monitoring runtime.")
    parser.add_argument(
        "--source",
        default="fake_face",
        choices=["fake_face", "fake_camera", "opencv_camera"],
        help="Emotion source.",
    )
    parser.add_argument(
        "--pattern",
        choices=["neutral", "tired", "sad", "anxious", "mixed"],
        default="tired",
        help="Fake face pattern.",
    )
    parser.add_argument("--count", type=parse_count, default=5, help="Number of samples, or None for infinite.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between samples.")
    parser.add_argument("--host", default="127.0.0.1", help="Base station host.")
    parser.add_argument("--port", type=int, default=8765, help="Base station /agent port.")
    parser.add_argument("--db-path", default="agent/data/xiao_an.db", help="SQLite database path.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--camera-width", type=int, default=None, help="Optional OpenCV camera width.")
    parser.add_argument("--camera-height", type=int, default=None, help="Optional OpenCV camera height.")
    parser.add_argument(
        "--model-backend",
        choices=["mock", "openvino", "qwen_vl"],
        default="mock",
        help="Face emotion model backend for camera sources.",
    )
    parser.add_argument("--model-path", default=None, help="OpenVINO face emotion model path.")
    parser.add_argument("--device", default="CPU", help="OpenVINO device name.")
    parser.add_argument("--fresh-db", action="store_true", help="Use a fresh temporary SQLite database for this run.")
    parser.add_argument("--verbose", action="store_true", help="Print each sample and result.")
    return parser.parse_args(argv)


async def main(args: argparse.Namespace | None = None) -> None:
    if args is None:
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
            camera_index=args.camera_index,
            camera_width=args.camera_width,
            camera_height=args.camera_height,
            model_backend=args.model_backend,
            model_path=args.model_path,
            device=args.device,
        )
        try:
            await runtime.run()
        finally:
            runtime.event_loop.brain.close()


def run_cli(argv: list[str] | None = None) -> int:
    try:
        asyncio.run(main(parse_args(argv)))
    except KeyboardInterrupt:
        raise
    except EXPECTED_CLI_ERRORS as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
