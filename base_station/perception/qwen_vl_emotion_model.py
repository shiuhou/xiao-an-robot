"""Qwen VL emotion model interface and fake implementation.

This module defines the future Qwen2.5-VL integration surface without pulling
in torch, transformers, or any real model dependency.
"""

from __future__ import annotations

import time


PATTERN_PREDICTIONS = {
    "neutral": {
        "emotion_tag": "neutral",
        "confidence": 0.55,
        "fatigue_score": 0.15,
        "visual_reason": "Face appears relaxed with no visible fatigue cues.",
        "vlm_observation": "The user looks calm and attentive.",
    },
    "tired": {
        "emotion_tag": "tired",
        "confidence": 0.9,
        "fatigue_score": 0.86,
        "visual_reason": "Eyes appear heavy and posture suggests fatigue.",
        "vlm_observation": "The user may need a short rest.",
    },
    "sad": {
        "emotion_tag": "sad",
        "confidence": 0.84,
        "fatigue_score": 0.35,
        "visual_reason": "Facial expression appears downcast.",
        "vlm_observation": "The user may be feeling sad or low.",
    },
    "anxious": {
        "emotion_tag": "anxious",
        "confidence": 0.88,
        "fatigue_score": 0.45,
        "visual_reason": "Expression appears tense and uneasy.",
        "vlm_observation": "The user may be anxious or stressed.",
    },
}

MIXED_PATTERN = ["neutral", "tired", "sad", "anxious", "neutral"]


class QwenVLEmotionModel:
    """Future Qwen VL emotion prediction interface."""

    def predict(self, frame: dict, context: dict | None = None) -> dict:
        """Predict emotion from a visual frame and optional context."""
        raise NotImplementedError


class FakeQwenVLEmotionModel(QwenVLEmotionModel):
    """Deterministic fake Qwen VL model for local tests and integration design."""

    def __init__(self, pattern: str = "neutral"):
        if pattern not in {"neutral", "tired", "sad", "anxious", "mixed"}:
            raise ValueError(f"Unsupported Qwen VL emotion pattern: {pattern}")
        self.pattern = pattern
        self._prediction_count = 0

    def _resolve_pattern(self) -> str:
        if self.pattern == "mixed":
            return MIXED_PATTERN[self._prediction_count % len(MIXED_PATTERN)]
        return self.pattern

    def predict(self, frame: dict, context: dict | None = None) -> dict:
        pattern = self._resolve_pattern()
        self._prediction_count += 1

        prediction = PATTERN_PREDICTIONS[pattern].copy()
        prediction.update({
            "source": "fake_qwen_vl",
            "frame_source": frame.get("source"),
            "frame_id": frame.get("frame_id"),
            "timestamp_ms": frame.get("timestamp_ms", int(time.time() * 1000)),
        })
        return prediction
