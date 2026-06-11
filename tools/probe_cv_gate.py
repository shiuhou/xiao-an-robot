"""Probe mock CV output and VLM trigger-gate decisions."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from base_station.perception.face_emotion_model import MockFaceEmotionModel
from base_station.perception.face_emotion_pipeline import FaceEmotionPipeline
from base_station.perception.fake_camera import FakeCameraFrameSource
from base_station.perception.opencv_camera import OpenCVCameraFrameSource
from base_station.perception.vlm_trigger_gate import VLMTriggerGate


STABLE_KEYS = (
    "frame_id",
    "timestamp_ms",
    "frame_source",
    "emotion_tag",
    "cv_emotion_raw",
    "confidence",
    "fatigue_score",
    "face_detected",
    "calibrated",
    "source",
    "gate_triggered",
    "gate_reason",
)


class ProbeOpenCVCameraFrameSource(OpenCVCameraFrameSource):
    """Tool-local adapter that adds optional FPS configuration."""

    def __init__(
        self,
        camera_index: int = 0,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
    ):
        super().__init__(camera_index=camera_index, width=width, height=height)
        self.fps = fps

    def open(self) -> None:
        super().open()
        if self.fps is not None and self._capture is not None:
            try:
                import cv2  # type: ignore[import-not-found]
            except ImportError:
                return
            self._capture.set(cv2.CAP_PROP_FPS, self.fps)


def parse_count(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--count must be non-negative")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe camera CV output and VLM gate decisions.")
    parser.add_argument("--source", choices=["fake_camera", "opencv_camera"], default="fake_camera", help="Frame source.")
    parser.add_argument("--model-backend", choices=["mock"], default="mock", help="CV model backend.")
    parser.add_argument(
        "--pattern",
        choices=["neutral", "tired", "anxious", "mixed"],
        default="neutral",
        help="Mock emotion pattern.",
    )
    parser.add_argument("--count", type=parse_count, default=10, help="Number of frames to process.")
    parser.add_argument("--interval", type=float, default=0.0, help="Seconds between fake frames.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--width", type=int, default=None, help="Optional OpenCV camera width.")
    parser.add_argument("--height", type=int, default=None, help="Optional OpenCV camera height.")
    parser.add_argument("--fps", type=int, default=None, help="Optional OpenCV camera FPS request.")
    parser.add_argument("--enable-gate", action="store_true", help="Evaluate VLMTriggerGate for each frame.")
    parser.add_argument("--force-gate", action="store_true", help="Force gate trigger when gate is enabled.")
    parser.add_argument("--no-show", action="store_true", help="Do not open an OpenCV display window.")
    parser.add_argument("--save-jsonl", default=None, help="Optional JSON Lines output path.")
    return parser.parse_args(argv)


def build_frame_source(args: argparse.Namespace):
    if args.source == "fake_camera":
        return FakeCameraFrameSource(count=args.count, interval_seconds=args.interval)
    if args.source == "opencv_camera":
        source_class = ProbeOpenCVCameraFrameSource if args.fps is not None else OpenCVCameraFrameSource
        kwargs = {
            "camera_index": args.camera_index,
            "width": args.width,
            "height": args.height,
        }
        if source_class is ProbeOpenCVCameraFrameSource:
            kwargs["fps"] = args.fps
        return source_class(
            **kwargs,
        )
    raise ValueError(f"Unsupported source: {args.source}")


def build_model(args: argparse.Namespace) -> MockFaceEmotionModel:
    if args.model_backend != "mock":
        raise ValueError(f"Unsupported model backend: {args.model_backend}")
    return MockFaceEmotionModel(pattern=args.pattern)


def normalize_probe_row(sample: dict, gate_result: dict | None, latency_ms: float | None = None) -> dict:
    row = {
        "frame_id": sample.get("frame_id"),
        "timestamp_ms": sample.get("timestamp_ms"),
        "frame_source": sample.get("frame_source"),
        "emotion_tag": sample.get("emotion_tag", sample.get("emotion")),
        "cv_emotion_raw": sample.get("cv_emotion_raw"),
        "confidence": sample.get("confidence"),
        "fatigue_score": sample.get("fatigue_score"),
        "face_detected": sample.get("face_detected"),
        "calibrated": sample.get("calibrated"),
        "source": sample.get("source"),
        "gate_triggered": None,
        "gate_reason": None,
        "latency_ms": latency_ms,
    }
    if gate_result is not None:
        row["gate_triggered"] = bool(gate_result.get("should_trigger", False))
        row["gate_reason"] = gate_result.get("reason")
        row["gate_raw"] = gate_result.copy()
    return row


def print_summary(row: dict) -> None:
    print(
        "frame={frame_id} emotion={emotion_tag} conf={confidence} "
        "fatigue={fatigue_score} gate={gate_triggered} reason={gate_reason}".format(**row)
    )


def draw_overlay(frame: dict, row: dict, cv2_module=None):
    cv2 = cv2_module
    if cv2 is None:
        try:
            import cv2 as imported_cv2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError("OpenCV display requires opencv-python to be installed.") from exc
        cv2 = imported_cv2
    payload = frame.get("payload")
    if payload is None:
        try:
            import numpy as np
        except ImportError as exc:
            raise ImportError("OpenCV display requires numpy when frame payload is missing.") from exc
        payload = np.zeros((frame.get("height") or 480, frame.get("width") or 640, 3), dtype=np.uint8)

    lines = [
        f"frame_id: {row.get('frame_id')}",
        f"emotion: {row.get('emotion_tag')} raw: {row.get('cv_emotion_raw')}",
        f"confidence: {row.get('confidence')} fatigue: {row.get('fatigue_score')}",
        f"face_detected: {row.get('face_detected')} calibrated: {row.get('calibrated')}",
        f"gate: {row.get('gate_triggered')} reason: {row.get('gate_reason')}",
        f"latency_ms: {row.get('latency_ms')}",
    ]
    for index, text in enumerate(lines):
        cv2.putText(
            payload,
            text,
            (20, 30 + index * 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2,
        )
    return payload


def show_frame(frame: dict, row: dict) -> bool:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return False

    display_frame = draw_overlay(frame, row, cv2_module=cv2)
    cv2.imshow("cv-gate-probe", display_frame)
    key = cv2.waitKey(1) & 0xFF
    return key == ord("q")


def close_display() -> None:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return
    cv2.destroyAllWindows()


async def probe_cv_gate(args: argparse.Namespace) -> list[dict]:
    frame_source = build_frame_source(args)
    model = build_model(args)
    pipeline = FaceEmotionPipeline(pattern=args.pattern, model=model)
    gate = VLMTriggerGate() if args.enable_gate else None
    rows: list[dict] = []

    jsonl_file = None
    if args.save_jsonl:
        output_path = Path(args.save_jsonl)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_file = output_path.open("w", encoding="utf-8")

    try:
        processed = 0
        async for frame in frame_source.frames():
            started = time.monotonic()
            sample = pipeline.process_frame(frame)
            gate_result = gate.evaluate(sample, force_vlm=args.force_gate) if gate is not None else None
            row = normalize_probe_row(sample, gate_result, latency_ms=round((time.monotonic() - started) * 1000, 3))
            rows.append(row)
            processed += 1
            print_summary(row)
            if jsonl_file is not None:
                jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            if not args.no_show:
                if show_frame(frame, row):
                    break
            if args.source == "opencv_camera" and processed >= args.count:
                break
    finally:
        if jsonl_file is not None:
            jsonl_file.close()
        close = getattr(frame_source, "close", None)
        if callable(close):
            close()
        if not args.no_show:
            close_display()

    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        asyncio.run(probe_cv_gate(args))
    except (ImportError, RuntimeError, ValueError) as exc:
        print(f"CV gate probe failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
