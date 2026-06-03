"""Face emotion pipeline skeleton.

This module maps camera-like frame dictionaries into emotion sample dictionaries
without using OpenCV, numpy, OpenVINO, or real model inference.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


PATTERN_SAMPLES = {
    "neutral": {
        "emotion_tag": "neutral",
        "confidence": 0.5,
        "fatigue_score": 0.2,
    },
    "tired": {
        "emotion_tag": "tired",
        "confidence": 0.9,
        "fatigue_score": 0.85,
    },
    "anxious": {
        "emotion_tag": "anxious",
        "confidence": 0.88,
        "fatigue_score": 0.4,
    },
}

MIXED_PATTERN = ["neutral", "tired", "tired", "neutral", "anxious"]


class FaceEmotionPipeline:
    """Skeleton face emotion pipeline with deterministic fake outputs."""

    def __init__(self, pattern: str = "neutral"):
        if pattern not in {"neutral", "tired", "anxious", "mixed"}:
            raise ValueError(f"Unsupported face emotion pattern: {pattern}")
        self.pattern = pattern
        self._frame_count = 0

    def _resolve_pattern(self) -> str:
        if self.pattern == "mixed":
            return MIXED_PATTERN[self._frame_count % len(MIXED_PATTERN)]
        return self.pattern

    def process_frame(self, frame: dict) -> dict:
        pattern = self._resolve_pattern()
        self._frame_count += 1
        sample = PATTERN_SAMPLES[pattern].copy()
        sample.update({
            "source": "fake_face",
            "frame_id": frame.get("frame_id"),
            "timestamp_ms": frame.get("timestamp_ms"),
        })
        return sample


FakeFaceEmotionPipeline = FaceEmotionPipeline


class CameraEmotionSource:
    """Adapt a frame source and pipeline into an async emotion sample source."""

    def __init__(self, frame_source: Any, pipeline: FaceEmotionPipeline):
        self.frame_source = frame_source
        self.pipeline = pipeline

    async def samples(self) -> AsyncIterator[dict]:
        async for frame in self.frame_source.frames():
            yield self.pipeline.process_frame(frame)
