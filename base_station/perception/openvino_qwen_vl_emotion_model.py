"""Emotion model wrapper for an OpenVINO Qwen VL runner."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from base_station.perception.qwen_vl_openvino_runner import build_emotion_analysis_prompt


ALLOWED_EMOTIONS = {"neutral", "tired", "sad", "anxious", "stressed", "happy", "unknown"}
EMOTION_ALIASES = {
    "neutral": "neutral",
    "calm": "neutral",
    "tired": "tired",
    "sleepy": "tired",
    "fatigue": "tired",
    "fatigued": "tired",
    "sad": "sad",
    "down": "sad",
    "downcast": "sad",
    "anxious": "anxious",
    "nervous": "anxious",
    "stressed": "stressed",
    "frustrated": "stressed",
    "angry": "stressed",
    "irritable": "stressed",
    "happy": "happy",
    "unknown": "unknown",
}


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

        emotion_tag = self._normalize_emotion_tag(prediction.get("emotion_tag"))

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
            "width": frame.get("width"),
            "height": frame.get("height"),
        }

    @staticmethod
    def _parse_json_output(raw_output: str) -> dict:
        text = str(raw_output).strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        elif "{" in text:
            text = OpenVINOQwenVLEmotionModel._extract_first_json_object(text)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse Qwen VL JSON output: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("Qwen VL JSON output must be an object.")
        return parsed

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        start = text.find("{")
        if start < 0:
            raise ValueError("Failed to parse Qwen VL JSON output: no JSON object found")

        in_string = False
        escaped = False
        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]

        raise ValueError("Failed to parse Qwen VL JSON output: unterminated JSON object")

    @staticmethod
    def _normalize_emotion_tag(value: Any) -> str:
        tag = str(value or "unknown").strip().lower()
        return EMOTION_ALIASES.get(tag, "unknown")

    @staticmethod
    def _clamp_float(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        return max(0.0, min(1.0, number))
