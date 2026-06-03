"""Fake face emotion source for local development."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from base_station.perception.emotion_source import EmotionSource


PATTERN_SAMPLES = {
    "neutral": {
        "source": "fake_face",
        "emotion_tag": "neutral",
        "confidence": 0.5,
        "fatigue_score": 0.2,
    },
    "tired": {
        "source": "fake_face",
        "emotion_tag": "tired",
        "confidence": 0.9,
        "fatigue_score": 0.85,
    },
    "anxious": {
        "source": "fake_face",
        "emotion_tag": "anxious",
        "confidence": 0.88,
        "fatigue_score": 0.4,
    },
}

MIXED_PATTERN = ["neutral", "tired", "tired", "neutral", "anxious"]


class FakeFaceEmotionSource(EmotionSource):
    """Generate deterministic fake face emotion samples."""

    def __init__(
        self,
        pattern: str = "tired",
        count: int | None = 5,
        interval_seconds: float = 1.0,
    ):
        if pattern not in {"neutral", "tired", "anxious", "mixed"}:
            raise ValueError(f"Unsupported fake emotion pattern: {pattern}")
        self.pattern = pattern
        self.count = count
        self.interval_seconds = interval_seconds

    def build_sample(self, index: int) -> dict:
        pattern = self.pattern
        if pattern == "mixed":
            pattern = MIXED_PATTERN[index % len(MIXED_PATTERN)]
        return PATTERN_SAMPLES[pattern].copy()

    async def samples(self) -> AsyncIterator[dict]:
        index = 0
        while self.count is None or index < self.count:
            yield self.build_sample(index)
            index += 1
            if self.interval_seconds > 0:
                await asyncio.sleep(self.interval_seconds)
