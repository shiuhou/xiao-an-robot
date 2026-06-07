"""Placeholder runner for future OpenVINO Qwen VL deployment."""

from __future__ import annotations

import json


EMOTION_TAGS = ("neutral", "tired", "sad", "anxious", "stressed", "happy", "unknown")
OUTPUT_FIELDS = ("emotion_tag", "confidence", "fatigue_score", "visual_reason", "vlm_observation")


class QwenVLOpenVINORunner:
    """Configuration shell for an OpenVINO/Optimum Intel Qwen2.5-VL runner."""

    def __init__(
        self,
        model_dir: str,
        device: str = "AUTO",
        max_new_tokens: int = 128,
    ):
        if not model_dir:
            raise ValueError("model_dir must not be empty.")
        if max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be greater than 0.")

        self.model_dir = model_dir
        self.device = device
        self.max_new_tokens = max_new_tokens

    def load(self) -> None:
        raise NotImplementedError(
            "Loading requires an OpenVINO / Optimum Intel exported Qwen2.5-VL model and is not implemented yet."
        )

    def generate(self, image, prompt: str, context: dict | None = None) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty.")
        raise NotImplementedError("Qwen2.5-VL OpenVINO generation is not implemented yet.")


def build_emotion_analysis_prompt(context: dict | None = None) -> str:
    lines = [
        "Analyze the user's visible emotional state from the image.",
        "Return JSON only, with these fields:",
        json.dumps({field: "<value>" for field in OUTPUT_FIELDS}, ensure_ascii=False),
        "emotion_tag must be one of: " + ", ".join(EMOTION_TAGS) + ".",
        "confidence and fatigue_score must be numbers from 0.0 to 1.0.",
        "visual_reason should explain visible evidence briefly.",
        "vlm_observation should summarize the user's apparent state briefly.",
    ]

    if context:
        lines.append("Context summary:")
        for key in ("cv", "vlm", "asr", "history"):
            if key in context:
                lines.append(f"{key}: {json.dumps(context[key], ensure_ascii=False, sort_keys=True)}")

    return "\n".join(lines)
