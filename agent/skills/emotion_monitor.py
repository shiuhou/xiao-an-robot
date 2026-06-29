"""Emotion monitor skill for the local simulation MVP.

This module uses simple threshold rules and an optional SQLite-backed memory
object. It does not depend on OpenClaw, LLMs, OpenVINO, ASR, or TTS synthesis.
"""

from __future__ import annotations

import time
import math
from typing import Any

from agent.skills.robot_motion import RobotMotionSkill


CARE_MESSAGES = {
    "fatigue": "你已经工作很久了，休息一下吧。",
    "fatigue_window": "你已经工作很久了，休息一下吧。",
    "negative_emotion_window": "我感觉你最近状态有点紧绷，我们先休息一下吧。",
    "anxious": "我感觉你有点紧张，要不要先慢慢呼吸一下？",
    "sad": "我感觉你有点低落，我陪你休息一下吧。",
    "stressed": "看起来压力有点大，我们先停下来放松一下吧。",
    "tired": "你看起来有点累了，先休息一下吧。",
}

WATCHED_EMOTIONS = {"anxious", "sad", "stressed", "tired"}
VALID_SOURCES = {"face", "voice"}
OPENFACE_FATIGUE_SOURCES = {"openface_fatigue_metrics", "openface", "openface_ov"}
LOW_QUALITY_STATES = {"low", "insufficient_evidence"}


def _clamp_0_100(value: float) -> float:
    return max(0.0, min(100.0, value))


def _is_openface_fatigue_sample(sample: dict[str, Any]) -> bool:
    source = str(sample.get("source", "") or "").lower()
    algorithm_version = str(sample.get("algorithm_version", "") or "").lower()
    return source in OPENFACE_FATIGUE_SOURCES or algorithm_version == "rule_v0"


def _has_insufficient_fatigue_evidence(sample: dict[str, Any]) -> bool:
    fatigue_level = str(sample.get("fatigue_level", "") or "").lower()
    if fatigue_level == "insufficient_evidence":
        return True

    observation_quality = sample.get("observation_quality")
    if isinstance(observation_quality, str):
        return observation_quality.strip().lower() in LOW_QUALITY_STATES

    if _is_openface_fatigue_sample(sample) and observation_quality is not None:
        try:
            return float(observation_quality) < 0.5
        except (TypeError, ValueError):
            return False

    return False


def normalize_fatigue_score_100(sample_or_score: Any) -> float | None:
    """Return fatigue score on a 0..100 scale, or None for missing/invalid evidence.

    OpenFace Route A samples already use 0..100. Legacy mock/VLM-like samples may
    still use 0..1, so fractional scores are scaled for backward compatibility.
    Out-of-range numeric values are clamped to keep the care layer bounded.
    Nested VLM scores are deliberately ignored; the primary sample owns care.
    """

    sample = sample_or_score if isinstance(sample_or_score, dict) else None
    raw_score = sample.get("fatigue_score") if sample is not None else sample_or_score

    if sample is not None and _has_insufficient_fatigue_evidence(sample):
        return None
    if raw_score is None:
        return None

    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score):
        return None

    if sample is not None and _is_openface_fatigue_sample(sample):
        return _clamp_0_100(score)
    if 0.0 <= score <= 1.0:
        return score * 100.0
    return _clamp_0_100(score)


class EmotionMonitorSkill:
    """Decide whether an emotion trigger should cause robot care actions."""

    name = "emotion_monitor"

    def __init__(
        self,
        gateway: Any | None = None,
        memory: Any | None = None,
        window_seconds: int = 300,
        avg_fatigue_threshold: float = 67.0,
        negative_count_threshold: int = 2,
        cooldown_seconds: int = 300,
        fatigue_threshold: float = 67.0,
        negative_confidence_threshold: float = 0.65,
    ):
        self.gateway = gateway
        self.memory = memory
        self.window_seconds = window_seconds
        self.avg_fatigue_threshold = avg_fatigue_threshold
        self.negative_count_threshold = negative_count_threshold
        self.cooldown_seconds = cooldown_seconds
        self.fatigue_threshold = fatigue_threshold
        self.negative_confidence_threshold = negative_confidence_threshold
        self._last_intervention_ms: int | None = None
        self.robot_motion = RobotMotionSkill(gateway=gateway)

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _parse_trigger(self, trigger: dict) -> dict[str, Any]:
        payload = trigger.get("payload", trigger)
        source = str(payload.get("source", "face")).lower()
        if source not in VALID_SOURCES:
            source = "face"

        return {
            "source": source,
            "emotion": str(payload.get("emotion_tag") or payload.get("emotion") or "normal").lower(),
            "confidence": float(payload.get("confidence", 0.0) or 0.0),
            "fatigue_score": normalize_fatigue_score_100(payload),
        }

    def _has_memory_db(self) -> bool:
        return (
            self.memory is not None
            and hasattr(self.memory, "insert_emotion")
            and hasattr(self.memory, "get_recent_summary")
        )

    def _is_in_cooldown(self, now_ms: int) -> bool:
        if self._last_intervention_ms is None:
            return False
        return now_ms - self._last_intervention_ms < self.cooldown_seconds * 1000

    def should_intervene(self, trigger: dict) -> tuple[bool, str, str]:
        parsed = self._parse_trigger(trigger)
        emotion = parsed["emotion"]
        confidence = parsed["confidence"]
        fatigue_score = parsed["fatigue_score"]

        if fatigue_score is not None and fatigue_score >= self.fatigue_threshold:
            return True, "fatigue", CARE_MESSAGES["fatigue"]

        if emotion in WATCHED_EMOTIONS and confidence >= self.negative_confidence_threshold:
            return True, emotion, CARE_MESSAGES[emotion]

        return False, "normal", ""

    def _should_intervene_from_summary(self, summary: dict[str, Any]) -> tuple[bool, str, str]:
        avg_fatigue = normalize_fatigue_score_100(summary.get("avg_fatigue_score"))
        if avg_fatigue is not None and avg_fatigue >= self.avg_fatigue_threshold:
            return True, "fatigue_window", CARE_MESSAGES["fatigue_window"]

        emotions_count = summary.get("emotions_count", {}) or {}
        negative_count = sum(int(emotions_count.get(emotion, 0) or 0) for emotion in WATCHED_EMOTIONS)
        if negative_count >= self.negative_count_threshold:
            return True, "negative_emotion_window", CARE_MESSAGES["negative_emotion_window"]

        return False, "normal", ""

    async def run(self, trigger: dict) -> dict:
        if self._has_memory_db():
            parsed = self._parse_trigger(trigger)
            self.memory.insert_emotion(
                source=parsed["source"],
                emotion_tag=parsed["emotion"],
                confidence=parsed["confidence"],
                fatigue_score=parsed["fatigue_score"],
            )
            summary = self.memory.get_recent_summary(seconds=self.window_seconds)
            should_handle, reason, text = self._should_intervene_from_summary(summary)
        else:
            should_handle, reason, text = self.should_intervene(trigger)

        if not should_handle:
            return {
                "handled": False,
                "reason": reason,
                "message": "No intervention needed.",
            }

        now_ms = self._now_ms()
        if self._is_in_cooldown(now_ms):
            return {
                "handled": False,
                "reason": "cooldown",
                "message": "Intervention skipped due to cooldown.",
            }

        actions = await self.robot_motion.care_for_user(text)
        self._last_intervention_ms = now_ms
        return {
            "handled": True,
            "reason": reason,
            "message": text,
            "actions": actions,
        }
