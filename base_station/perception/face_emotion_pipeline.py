"""Face emotion pipeline skeleton.

This module maps camera-like frame dictionaries into emotion sample dictionaries
without using OpenCV, numpy, OpenVINO, or real model inference.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from base_station.perception.face_emotion_model import FaceEmotionModel, MockFaceEmotionModel


class FaceEmotionPipeline:
    """Skeleton face emotion pipeline with deterministic fake outputs."""

    def __init__(self, pattern: str = "neutral", model: FaceEmotionModel | None = None):
        self.pattern = pattern
        self.model = model or MockFaceEmotionModel(pattern=pattern)

    def process_frame(self, frame: dict) -> dict:
        sample = self.model.predict(frame).copy()
        sample.update({
            "source": sample.get("source") or "fake_face",
            "frame_source": frame.get("source"),
            "frame_id": frame.get("frame_id"),
            "timestamp_ms": frame.get("timestamp_ms"),
            "width": frame.get("width"),
            "height": frame.get("height"),
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
