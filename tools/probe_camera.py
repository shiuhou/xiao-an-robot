"""Probe OpenCV camera capture without opening a GUI window."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from base_station.perception.opencv_camera import OpenCVCameraFrameSource


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe OpenCV camera frame capture.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--camera-width", type=int, default=None, help="Optional camera width.")
    parser.add_argument("--camera-height", type=int, default=None, help="Optional camera height.")
    parser.add_argument("--count", type=int, default=10, help="Number of frames to read.")
    parser.add_argument("--interval", type=float, default=0.2, help="Seconds between frame reads.")
    parser.add_argument("--verbose", action="store_true", help="Print full frame metadata.")
    return parser.parse_args(argv)


def build_summary(frames: list[dict], duration_seconds: float) -> dict:
    last_frame = frames[-1] if frames else {}
    total_frames = len(frames)
    return {
        "total_frames": total_frames,
        "duration_seconds": duration_seconds,
        "approx_fps": total_frames / duration_seconds if duration_seconds > 0 else 0.0,
        "width": last_frame.get("width"),
        "height": last_frame.get("height"),
    }


def print_frame(frame: dict, verbose: bool = False) -> None:
    metadata = {
        "frame_id": frame["frame_id"],
        "source": frame["source"],
        "width": frame["width"],
        "height": frame["height"],
        "timestamp_ms": frame["timestamp_ms"],
    }
    if verbose:
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        return

    print(
        "frame_id={frame_id} source={source} width={width} "
        "height={height} timestamp_ms={timestamp_ms}".format(**metadata)
    )


def probe_camera(args: argparse.Namespace) -> dict:
    frames = []
    start = time.monotonic()
    with OpenCVCameraFrameSource(
        camera_index=args.camera_index,
        width=args.camera_width,
        height=args.camera_height,
    ) as source:
        for index in range(args.count):
            frame = source.read_frame()
            frames.append(frame)
            print_frame(frame, verbose=args.verbose)
            if args.interval > 0 and index < args.count - 1:
                time.sleep(args.interval)

    duration_seconds = time.monotonic() - start
    summary = build_summary(frames, duration_seconds)
    print("summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        probe_camera(args)
    except ImportError as exc:
        print(f"Camera probe failed: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Camera probe failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
