"""Emotion model wrapper for an OpenVINO Qwen VL runner."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from base_station.perception.qwen_vl_openvino_runner import build_emotion_analysis_prompt


ALLOWED_EMOTIONS = {"neutral", "tired", "sad", "anxious", "stressed", "happy", "unknown"}


class OpenVINOQwenVLEmotionModel:
    """Convert Qwen VL runner JSON output into the project emotion sample format."""

    def __init__(self, runner: Any):
        if runner is None:
            raise ValueError("runner must not be None.")
        self.runner = runner

    def predict(self, frame: dict, context: dict | None = None) -> dict:
        prompt = build_emotion_analysis_prompt(context)
        image = frame.get("payload", frame)
        raw_output = self.runner.generate(image, prompt, context=context)
        prediction = self._parse_json_output(raw_output)

        emotion_tag = str(prediction.get("emotion_tag", "unknown") or "unknown")
        if emotion_tag not in ALLOWED_EMOTIONS:
            emotion_tag = "unknown"

        return {
            "emotion_tag": emotion_tag,
            "confidence": self._clamp_float(prediction.get("confidence", 0.0)),
            "fatigue_score": self._clamp_float(prediction.get("fatigue_score", 0.0)),
            "visual_reason": str(prediction.get("visual_reason", "") or ""),
            "vlm_observation": str(prediction.get("vlm_observation", "") or ""),
            "source": "openvino_qwen_vl",
            "frame_source": frame.get("source"),
            "frame_id": frame.get("frame_id"),
            "timestamp_ms": frame.get("timestamp_ms", int(time.time() * 1000)),
        }

    @staticmethod
    def _parse_json_output(raw_output: str) -> dict:
        text = str(raw_output).strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse Qwen VL JSON output: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("Qwen VL JSON output must be an object.")
        return parsed

    @staticmethod
    def _clamp_float(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        return max(0.0, min(1.0, number))
