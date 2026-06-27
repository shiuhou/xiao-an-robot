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
    parser.add_argument(
        "--scan-indices",
        default=None,
        help="Comma-separated OpenCV camera indices to probe, for example 0,1,2.",
    )
    parser.add_argument("--camera-width", type=int, default=None, help="Optional camera width.")
    parser.add_argument("--camera-height", type=int, default=None, help="Optional camera height.")
    parser.add_argument("--count", type=int, default=10, help="Number of frames to read.")
    parser.add_argument("--interval", type=float, default=0.2, help="Seconds between frame reads.")
    parser.add_argument("--verbose", action="store_true", help="Print full frame metadata.")
    return parser.parse_args(argv)


def parse_scan_indices(value: str | None) -> list[int]:
    if value is None or not value.strip():
        return []
    indices = []
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        indices.append(int(part))
    return indices


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


def scan_camera_indices(args: argparse.Namespace) -> dict:
    available = []
    failed = []
    for camera_index in parse_scan_indices(args.scan_indices):
        probe_args = argparse.Namespace(
            camera_index=camera_index,
            camera_width=args.camera_width,
            camera_height=args.camera_height,
            count=1,
            interval=0,
            verbose=False,
        )
        try:
            summary = probe_camera(probe_args)
            available.append({
                "camera_index": camera_index,
                "width": summary.get("width"),
                "height": summary.get("height"),
            })
        except (ImportError, RuntimeError) as exc:
            message = str(exc)
            failed.append({
                "camera_index": camera_index,
                "error": message,
            })
            print(f"camera_index={camera_index} unavailable: {message}", file=sys.stderr)

    result = {
        "available": available,
        "failed": failed,
        "count": len(available),
    }
    print("scan_summary:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if parse_scan_indices(args.scan_indices):
            result = scan_camera_indices(args)
            return 0 if result["available"] else 1
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
