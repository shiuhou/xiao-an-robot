"""Send local test JPEG frames to the Xiao An /video WebSocket endpoint."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_video_packet(image_bgr, device_ts: int, jpeg_quality: int = 80) -> bytes:
    success, encoded = cv2.imencode(
        ".jpg",
        image_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
    )
    if not success:
        raise RuntimeError("Failed to encode test video frame as JPEG")

    jpeg = encoded.tobytes()
    return len(jpeg).to_bytes(4, "big") + int(device_ts).to_bytes(4, "big") + jpeg


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send test JPEG frames to a /video WebSocket endpoint.")
    parser.add_argument("--url", default="ws://127.0.0.1:8765/video", help="Target /video WebSocket URL.")
    parser.add_argument("--frames", type=int, default=5, help="Number of frames to send.")
    parser.add_argument("--fps", type=float, default=1.0, help="Frames per second.")
    parser.add_argument("--width", type=int, default=320, help="Frame width.")
    parser.add_argument("--height", type=int, default=240, help="Frame height.")
    parser.add_argument("--image-path", default=None, help="Optional image file to resize and send.")
    parser.add_argument("--jpeg-quality", type=int, default=80, help="JPEG quality from 0 to 100.")
    return parser.parse_args(argv)


def load_image(image_path: str | None, width: int, height: int, frame_index: int):
    if image_path:
        image = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Failed to read image: {image_path}")
        return cv2.resize(image, (width, height))

    image = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(
        image,
        f"frame {frame_index + 1}",
        (20, max(40, height // 2)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return image


async def send_frames(args: argparse.Namespace) -> None:
    if args.frames < 0:
        raise ValueError("--frames must be non-negative")
    if args.fps <= 0:
        raise ValueError("--fps must be positive")

    interval_seconds = 1.0 / args.fps
    async with websockets.connect(args.url) as websocket:
        for index in range(args.frames):
            image = load_image(args.image_path, args.width, args.height, index)
            device_ts = int(time.time() * 1000) & 0xFFFFFFFF
            packet = build_video_packet(
                image,
                device_ts=device_ts,
                jpeg_quality=args.jpeg_quality,
            )
            await websocket.send(packet)
            print(
                f"[send_test_video_frame] sent frame {index + 1}/{args.frames}, "
                f"bytes={len(packet)}"
            )
            if index < args.frames - 1:
                await asyncio.sleep(interval_seconds)


def run_cli(argv: list[str] | None = None) -> int:
    try:
        asyncio.run(send_frames(parse_args(argv)))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
