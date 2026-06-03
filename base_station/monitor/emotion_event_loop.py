"""Emotion sample event loop for the base station MVP.

This module only adapts emotion samples into AgentBrain events. It does not
perform OpenVINO inference, camera capture, ASR, TTS, or any model work.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Iterable
from typing import Any


class EmotionEventLoop:
    """Forward base_station emotion samples to an AgentBrain-like object."""

    def __init__(self, brain: Any):
        self.brain = brain

    def build_event(self, sample: dict) -> dict:
        return {
            "type": "emotion.sample",
            "payload": {
                "source": sample.get("source", "simulator"),
                "emotion_tag": sample.get("emotion_tag", sample.get("emotion", "neutral")),
                "confidence": float(sample.get("confidence", 0.0) or 0.0),
                "fatigue_score": float(sample.get("fatigue_score", 0.0) or 0.0),
            },
        }

    async def handle_sample(self, sample: dict) -> dict:
        event = self.build_event(sample)
        return await self.brain.handle_event(event)

    async def run_stream(
        self,
        samples: AsyncIterable[dict] | Iterable[dict],
        interval_seconds: float | None = None,
    ) -> list[dict]:
        results = []

        if hasattr(samples, "__aiter__"):
            async for sample in samples:
                results.append(await self.handle_sample(sample))
                if interval_seconds is not None:
                    await asyncio.sleep(interval_seconds)
            return results

        for sample in samples:
            results.append(await self.handle_sample(sample))
            if interval_seconds is not None:
                await asyncio.sleep(interval_seconds)
        return results
