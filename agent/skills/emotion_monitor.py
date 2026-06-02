"""Emotion monitor skill for the local simulation MVP.

This module uses simple threshold rules only. It does not depend on OpenClaw,
LLMs, SQLite, OpenVINO, ASR, or TTS synthesis.
"""

from __future__ import annotations

from typing import Any

from agent.skills.robot_motion import RobotMotionSkill


CARE_MESSAGES = {
    "fatigue": "你已经工作很久了，休息一下吧。",
    "anxious": "我感觉你有点紧张，要不要先慢慢呼吸一下？",
    "sad": "我感觉你有点低落，我陪你休息一下吧。",
    "stressed": "看起来压力有点大，我们先停下来放松一下吧。",
    "tired": "你看起来有点累了，先休息一下吧。",
}

WATCHED_EMOTIONS = {"anxious", "sad", "stressed", "tired"}


class EmotionMonitorSkill:
    """Decide whether an emotion trigger should cause robot care actions."""

    name = "emotion_monitor"

    def __init__(self, gateway: Any | None = None, memory: Any | None = None):
        self.gateway = gateway
        self.memory = memory
        self.robot_motion = RobotMotionSkill(gateway=gateway)

    def should_intervene(self, trigger: dict) -> tuple[bool, str, str]:
        payload = trigger.get("payload", trigger)
        emotion = str(payload.get("emotion_tag") or payload.get("emotion") or "normal").lower()
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        fatigue_score = float(payload.get("fatigue_score", 0.0) or 0.0)

        if fatigue_score >= 0.7:
            return True, "fatigue", CARE_MESSAGES["fatigue"]

        if emotion in WATCHED_EMOTIONS and confidence >= 0.65:
            return True, emotion, CARE_MESSAGES[emotion]

        return False, "normal", ""

    async def run(self, trigger: dict) -> dict:
        should_handle, reason, text = self.should_intervene(trigger)
        if not should_handle:
            return {
                "handled": False,
                "reason": reason,
                "message": "No intervention needed.",
            }

        actions = await self.robot_motion.care_for_user(text)
        return {
            "handled": True,
            "reason": reason,
            "message": text,
            "actions": actions,
        }
