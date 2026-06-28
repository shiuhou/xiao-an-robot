"""Emotion sample event loop for the base station MVP.

This module only adapts emotion samples into AgentBrain events. It does not
perform OpenVINO inference, camera capture, ASR, TTS, or any model work.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Iterable
import json
from typing import Any


# Optional fields forwarded verbatim only when present, so legacy samples
# (source/emotion_tag/confidence/fatigue_score) produce an unchanged payload.
# Union of the perception contract fields (OpenFace Route A) and the
# memory/VLM context fields (asr-emotion-trigger).
OPTIONAL_PAYLOAD_FIELDS = (
    # perception contract (OpenFace cv_sample)
    "polarity",
    "fatigue_level",
    "observation_quality",
    "evidence_codes",
    "algorithm_version",
    "presence_state",
    "valence",
    "au_json",
    # frame metadata
    "frame_source",
    "frame_id",
    "timestamp_ms",
    "width",
    "height",
    # session/context
    "session_id",
    "project_id",
    # VLM gate / verdict
    "vlm_triggered",
    "vlm_trigger_reason",
    "visual_reason",
    "vlm_observation",
    # nested raw perception sample (present on VLM-triggered frames)
    "cv_sample",
    # normalized VLM result (present on VLM-triggered frames)
    "vlm",
    # CV/VLM fusion decision metadata
    "fusion",
)


class EmotionEventLoop:
    """Forward base_station emotion samples to an AgentBrain-like object."""

    def __init__(self, brain: Any):
        self.brain = brain

    @staticmethod
    def _coerce_fatigue_score(value):
        # insufficient_evidence carries None; preserve it (None must not become 0.0).
        if value is None:
            return None
        return float(value or 0.0)

    def build_event(self, sample: dict) -> dict:
        payload = {
            "source": sample.get("source", "simulator"),
            "emotion_tag": sample.get("emotion_tag", sample.get("emotion", "neutral")),
            "confidence": float(sample.get("confidence", 0.0) or 0.0),
            "fatigue_score": self._coerce_fatigue_score(sample.get("fatigue_score", 0.0)),
        }
        for field in OPTIONAL_PAYLOAD_FIELDS:
            if field in sample:
                payload[field] = sample[field]
        return {
            "type": "emotion.sample",
            "payload": payload,
        }

    async def handle_sample(self, sample: dict) -> dict:
        event = self.build_event(sample)
        print("[emotion.sample]", json.dumps(event, ensure_ascii=False))
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
