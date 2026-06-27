"""Static image frame source for camera-free perception smoke tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
import time
from typing import Any

from base_station.perception.frame_source import FrameSource


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class StaticImageFrameSource(FrameSource):
    """Load a local PNG/JPG/JPEG and emit camera-like frame dictionaries."""

    def __init__(
        self,
        image_path: str | Path,
        count: int | None = 1,
        interval_seconds: float = 0.0,
    ):
        self.image_path = Path(image_path)
        self.count = count
        self.interval_seconds = interval_seconds
        self._frame_id = 0

    def read_frame(self) -> dict:
        payload, width, height = load_static_image(self.image_path)
        self._frame_id += 1
        return {
            "source": "image_file",
            "frame_id": self._frame_id,
            "timestamp_ms": int(time.time() * 1000),
            "width": width,
            "height": height,
            "payload": payload,
        }

    async def frames(self) -> AsyncIterator[dict]:
        emitted = 0
        while self.count is None or emitted < self.count:
            yield self.read_frame()
            emitted += 1
            if self.interval_seconds > 0:
                await asyncio.sleep(self.interval_seconds)


def load_static_image(image_path: str | Path) -> tuple[Any, int, int]:
    """Decode a local image and return ``(payload, width, height)``."""

    path = Path(image_path)
    _validate_image_path(path)

    try:
        return _load_with_cv2(path)
    except ImportError:
        return _load_with_pillow(path)


def _validate_image_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Static image path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Static image path is not a file: {path}")
    if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(
            "Static image source supports only PNG/JPG/JPEG files; "
            f"got: {path.suffix or '<no extension>'}"
        )


def _load_with_cv2(path: Path) -> tuple[Any, int, int]:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError("opencv-python is not installed.") from exc

    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to decode static image with OpenCV: {path}")

    shape = getattr(image, "shape", None)
    if not shape or len(shape) < 2:
        raise ValueError(f"Decoded static image has invalid shape: {path}")
    return image, int(shape[1]), int(shape[0])


def _load_with_pillow(path: Path) -> tuple[Any, int, int]:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "StaticImageFrameSource requires opencv-python or Pillow to decode images."
        ) from exc

    try:
        image = Image.open(path)
        image.load()
    except Exception as exc:
        raise ValueError(f"Failed to decode static image with Pillow: {path}") from exc

    width, height = image.size
    return image, int(width), int(height)
