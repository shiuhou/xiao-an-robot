"""Emotion monitor skill for the local simulation MVP.

This module uses simple threshold rules and an optional SQLite-backed memory
object. It does not depend on OpenClaw, LLMs, OpenVINO, ASR, or TTS synthesis.
"""

from __future__ import annotations

import inspect
import time
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
HIGH_FATIGUE_LEVEL = "high"
DEFAULT_FATIGUE_THRESHOLD = 67.0


class EmotionMonitorSkill:
    """Decide whether an emotion trigger should cause robot care actions."""

    name = "emotion_monitor"

    def __init__(
        self,
        gateway: Any | None = None,
        memory: Any | None = None,
        window_seconds: int = 300,
        avg_fatigue_threshold: float = DEFAULT_FATIGUE_THRESHOLD,
        negative_count_threshold: int = 2,
        cooldown_seconds: int = 300,
        fatigue_threshold: float = DEFAULT_FATIGUE_THRESHOLD,
        negative_confidence_threshold: float = 0.65,
        execute_local_care: bool = True,
    ):
        self.gateway = gateway
        self.memory = memory
        self.window_seconds = window_seconds
        self.avg_fatigue_threshold = self._normalize_fatigue_score(avg_fatigue_threshold)
        self.negative_count_threshold = negative_count_threshold
        self.cooldown_seconds = cooldown_seconds
        self.fatigue_threshold = self._normalize_fatigue_score(fatigue_threshold)
        self.negative_confidence_threshold = negative_confidence_threshold
        self.execute_local_care = execute_local_care
        self._last_intervention_ms: int | None = None
        self.robot_motion = RobotMotionSkill(gateway=gateway)

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _normalize_fatigue_score(value: Any) -> float | None:
        if value is None:
            return None
        score = float(value)
        if 0.0 <= score <= 1.0:
            return score * 100.0
        return score

    def _parse_trigger(self, trigger: dict) -> dict[str, Any]:
        payload = trigger.get("payload", trigger)
        raw_source = str(payload.get("source", "face")).lower()
        source = raw_source
        if source not in VALID_SOURCES:
            source = "face"

        return {
            "source": source,
            "raw_source": raw_source,
            "emotion": str(payload.get("emotion_tag") or payload.get("emotion") or "normal").lower(),
            "confidence": float(payload.get("confidence", 0.0) or 0.0),
            "fatigue_score": self._normalize_fatigue_score(payload.get("fatigue_score")),
            "raw_fatigue_score": payload.get("fatigue_score"),
            "timestamp_ms": payload.get("timestamp_ms") or payload.get("timestamp"),
            "frame_source": payload.get("frame_source"),
            "frame_id": payload.get("frame_id"),
            "polarity": payload.get("polarity"),
            "valence": payload.get("valence"),
            "fatigue_level": str(payload.get("fatigue_level") or "").lower() or None,
            "observation_quality": payload.get("observation_quality"),
            "evidence_codes": payload.get("evidence_codes"),
            "algorithm_version": payload.get("algorithm_version"),
            "presence_state": payload.get("presence_state"),
            "au_json": payload.get("au_json"),
        }

    def _build_intervention_payload(
        self,
        parsed: dict[str, Any],
        reason: str,
        message: str,
        now_ms: int,
    ) -> dict[str, Any]:
        timestamp = parsed.get("timestamp_ms") or now_ms
        return {
            "emotion_tag": parsed["emotion"],
            "confidence": parsed["confidence"],
            "fatigue_score": parsed["raw_fatigue_score"],
            "reason": reason,
            "timestamp": timestamp,
            "timestamp_ms": timestamp,
            "source": parsed.get("raw_source") or parsed["source"],
            "frame_source": parsed.get("frame_source"),
            "frame_id": parsed.get("frame_id"),
            "message": message,
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

    def _insert_emotion(self, parsed: dict[str, Any]) -> None:
        arguments = {
            "source": parsed["source"],
            "emotion_tag": parsed["emotion"],
            "confidence": parsed["confidence"],
            "fatigue_score": parsed["fatigue_score"],
        }
        parameters = inspect.signature(self.memory.insert_emotion).parameters
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        for field in (
            "polarity",
            "valence",
            "fatigue_level",
            "observation_quality",
            "evidence_codes",
            "algorithm_version",
            "presence_state",
            "au_json",
        ):
            value = parsed.get(field)
            if value is not None and (accepts_kwargs or field in parameters):
                arguments[field] = value
        self.memory.insert_emotion(**arguments)

    def should_intervene(self, trigger: dict) -> tuple[bool, str, str]:
        parsed = self._parse_trigger(trigger)
        emotion = parsed["emotion"]
        confidence = parsed["confidence"]
        fatigue_score = parsed["fatigue_score"]
        fatigue_level = parsed["fatigue_level"]

        if fatigue_level == HIGH_FATIGUE_LEVEL:
            return True, "fatigue", CARE_MESSAGES["fatigue"]

        if (
            fatigue_score is not None
            and self.fatigue_threshold is not None
            and fatigue_score >= self.fatigue_threshold
        ):
            return True, "fatigue", CARE_MESSAGES["fatigue"]

        if emotion in WATCHED_EMOTIONS and confidence >= self.negative_confidence_threshold:
            return True, emotion, CARE_MESSAGES[emotion]

        return False, "normal", ""

    def _should_intervene_from_summary(self, summary: dict[str, Any]) -> tuple[bool, str, str]:
        fatigue_level_top = str(summary.get("fatigue_level_top") or "").lower()
        avg_fatigue = self._normalize_fatigue_score(summary.get("avg_fatigue_score"))
        if fatigue_level_top == HIGH_FATIGUE_LEVEL:
            return True, "fatigue_window", CARE_MESSAGES["fatigue_window"]

        if (
            avg_fatigue is not None
            and self.avg_fatigue_threshold is not None
            and avg_fatigue >= self.avg_fatigue_threshold
        ):
            return True, "fatigue_window", CARE_MESSAGES["fatigue_window"]

        emotions_count = summary.get("emotions_count", {}) or {}
        negative_count = sum(int(emotions_count.get(emotion, 0) or 0) for emotion in WATCHED_EMOTIONS)
        if negative_count >= self.negative_count_threshold:
            return True, "negative_emotion_window", CARE_MESSAGES["negative_emotion_window"]

        return False, "normal", ""

    async def run(self, trigger: dict) -> dict:
        parsed = self._parse_trigger(trigger)
        if self._has_memory_db():
            self._insert_emotion(parsed)
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

        payload = self._build_intervention_payload(parsed, reason, text, now_ms)
        self._last_intervention_ms = now_ms
        if not self.execute_local_care:
            return {
                "handled": True,
                "reason": reason,
                "message": text,
                "payload": payload,
            }

        actions = await self.robot_motion.care_for_user(text)
        return {
            "handled": True,
            "reason": reason,
            "message": text,
            "payload": payload,
            "actions": actions,
        }
