"""Lightweight gate for deciding when to run a VLM explanation model."""

from __future__ import annotations

from collections import deque


NEGATIVE_EMOTIONS = {"tired", "sad", "anxious", "stressed"}


class VLMTriggerGate:
    """Decide whether a CV sample should trigger VLM analysis.

    The gate reads the primary CV/OpenFace/mock sample. It does not consume a
    nested VLM prediction and it does not change the sample's top-level
    emotion_tag, confidence, or fatigue_score. OpenFace Route A fatigue scores
    are expected on a 0..100 scale, with 67+ treated as high fatigue.
    """

    def __init__(
        self,
        fatigue_threshold: float = 67.0,
        negative_confidence_threshold: float = 0.75,
        window_size: int = 10,
        negative_count_threshold: int = 4,
        negative_conf_sum_threshold: float = 2.0,
    ):
        self.fatigue_threshold = fatigue_threshold
        self.negative_confidence_threshold = negative_confidence_threshold
        self.window_size = window_size
        self.negative_count_threshold = negative_count_threshold
        self.negative_conf_sum_threshold = negative_conf_sum_threshold
        self._recent_negative_flags = deque(maxlen=max(1, window_size))
        self._recent_negative_confidences = deque(maxlen=max(1, window_size))

    def evaluate(self, sample: dict, force_vlm: bool = False) -> dict:
        emotion_tag = str(sample.get("emotion_tag", sample.get("emotion", "neutral")) or "neutral")
        confidence = float(sample.get("confidence", 0.0) or 0.0)
        fatigue_score = float(sample.get("fatigue_score", 0.0) or 0.0)
        is_negative = emotion_tag in NEGATIVE_EMOTIONS
        is_confident_negative = is_negative and confidence >= self.negative_confidence_threshold
        self._recent_negative_flags.append(is_negative)
        self._recent_negative_confidences.append(confidence if is_negative else 0.0)

        if force_vlm:
            return {"should_trigger": True, "reason": "force"}

        if fatigue_score >= self.fatigue_threshold:
            return {"should_trigger": True, "reason": "high_fatigue"}

        if is_confident_negative:
            return {"should_trigger": True, "reason": "negative_emotion"}

        negative_count = sum(self._recent_negative_flags)
        negative_conf_sum = sum(self._recent_negative_confidences)
        if (
            negative_count >= self.negative_count_threshold
            and negative_conf_sum >= self.negative_conf_sum_threshold
        ):
            return {"should_trigger": True, "reason": "negative_emotion_window"}

        return {"should_trigger": False, "reason": "normal"}
