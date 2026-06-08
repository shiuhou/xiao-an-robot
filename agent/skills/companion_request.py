"""Companion request skill driven by ASR text emotion triggers."""

from __future__ import annotations

from base_station.perception.asr_emotion_trigger import ASREmotionTrigger
from agent.skills.robot_motion import RobotMotionSkill


class CompanionRequestSkill:
    """Turn ASR companion/fatigue text cues into robot care actions."""

    name = "companion_request"

    def __init__(
        self,
        robot_motion: RobotMotionSkill | None = None,
        trigger: ASREmotionTrigger | None = None,
    ):
        self.robot_motion = robot_motion or RobotMotionSkill()
        self.trigger = trigger or ASREmotionTrigger()

    async def handle_text(self, text: str | None) -> dict:
        trigger_result = self.trigger.analyze(text)
        if not trigger_result["should_trigger"]:
            return {
                "handled": False,
                "reason": trigger_result["reason"],
                "trigger_result": trigger_result,
            }

        await self.robot_motion.care_for_user()
        return {
            "handled": True,
            "reason": "asr_emotion_triggered",
            "trigger_result": trigger_result,
        }
