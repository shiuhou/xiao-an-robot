"""Companion request skill driven by ASR text emotion triggers."""

from __future__ import annotations

from base_station.perception.asr_emotion_trigger import ASREmotionTrigger
from agent.skills.robot_motion import RobotMotionSkill


class CompanionRequestSkill:
    """Turn companion/fatigue text cues into an immediate robot pre-response."""

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

        actions = [
            await self.robot_motion.show_expression("caring"),
            await self.robot_motion.move_out_of_dock(),
        ]
        return {
            "handled": True,
            "reason": "asr_emotion_triggered",
            "trigger_result": trigger_result,
            "actions": actions,
        }
