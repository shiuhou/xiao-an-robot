"""Build unified emotion context for Agent and future LLM use."""

from __future__ import annotations

from copy import deepcopy


CV_FIELDS = (
    "emotion_tag",
    "confidence",
    "fatigue_score",
    "source",
    "frame_source",
    "frame_id",
    "timestamp_ms",
)

VLM_FIELDS = (
    "emotion_tag",
    "confidence",
    "fatigue_score",
    "visual_reason",
    "vlm_observation",
    "source",
    "frame_source",
    "frame_id",
    "timestamp_ms",
)

DEFAULT_HISTORY = {
    "count": 0,
    "avg_fatigue_score": 0.0,
    "top_emotion": None,
    "emotions_count": {},
}


class EmotionContextBuilder:
    """Combine CV, VLM, ASR, and history summary into one context dict."""

    def build(
        self,
        cv_sample: dict | None = None,
        vlm_sample: dict | None = None,
        asr_text: str | None = None,
        history_summary: dict | None = None,
    ) -> dict:
        return {
            "cv": self._pick_fields(cv_sample, CV_FIELDS),
            "vlm": self._pick_fields(vlm_sample, VLM_FIELDS),
            "asr": {"text": asr_text or ""},
            "history": self._build_history(history_summary),
        }

    @staticmethod
    def _pick_fields(sample: dict | None, fields: tuple[str, ...]) -> dict | None:
        if sample is None:
            return None
        return {field: sample.get(field) for field in fields}

    @staticmethod
    def _build_history(history_summary: dict | None) -> dict:
        if history_summary is None:
            return deepcopy(DEFAULT_HISTORY)

        history = deepcopy(DEFAULT_HISTORY)
        history.update(deepcopy(history_summary))
        return history
