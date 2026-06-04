"""Face emotion model interface and mock implementation.

This is a pre-OpenVINO seam: the runtime can depend on a small predict()
contract today, while a real model can replace MockFaceEmotionModel later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


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


class FaceEmotionModel(ABC):
    """Base interface for face emotion prediction models."""

    @abstractmethod
    def predict(self, frame: dict) -> dict:
        """Predict emotion fields for a frame."""
        raise NotImplementedError


class MockFaceEmotionModel(FaceEmotionModel):
    """Deterministic fake model used before OpenVINO integration."""

    def __init__(self, pattern: str = "neutral"):
        if pattern not in {"neutral", "tired", "anxious", "mixed"}:
            raise ValueError(f"Unsupported face emotion pattern: {pattern}")
        self.pattern = pattern
        self._prediction_count = 0

    def _resolve_pattern(self) -> str:
        if self.pattern == "mixed":
            return MIXED_PATTERN[self._prediction_count % len(MIXED_PATTERN)]
        return self.pattern

    def predict(self, frame: dict) -> dict:
        pattern = self._resolve_pattern()
        self._prediction_count += 1
        return PATTERN_SAMPLES[pattern].copy()
