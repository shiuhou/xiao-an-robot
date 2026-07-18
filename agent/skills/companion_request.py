"""Companion request skill driven by ASR text emotion triggers."""

from __future__ import annotations

import random
from collections.abc import Sequence

from base_station.perception.asr_emotion_trigger import ASREmotionTrigger
from agent.skills.robot_motion import RobotMotionSkill


PRE_RESPONSE_TEXT = "辛苦啦，小安靠近一点点，陪你慢慢喘口气。"
# Sent before OpenClaw follow-up; base_station streams these as robot-ready raw PCM.
PRE_RESPONSE_TEXTS = (
    "辛苦啦，小安靠近一点点，陪你慢慢喘口气。",
    "我在呢，先把肩膀放松，小安在旁边接住你。",
    "先停一下也可以，小安陪你缓一缓，不用硬撑。",
)
LOCAL_CARE_MOTION = {
    "speed": 0.56,
    "distance_cm": 10,
    "timeout_ms": 2600,
}


class CompanionRequestSkill:
    """Turn companion/fatigue text cues into an immediate robot pre-response."""

    name = "companion_request"

    def __init__(
        self,
        robot_motion: RobotMotionSkill | None = None,
        trigger: ASREmotionTrigger | None = None,
        pre_response_texts: Sequence[str] | None = None,
        rng: random.Random | None = None,
    ):
        self.robot_motion = robot_motion or RobotMotionSkill()
        self.trigger = trigger or ASREmotionTrigger()
        self.pre_response_texts = tuple(
            text.strip()
            for text in (pre_response_texts or PRE_RESPONSE_TEXTS)
            if str(text).strip()
        ) or (PRE_RESPONSE_TEXT,)
        self.rng = rng or random.Random()

    def pick_pre_response_text(self) -> str:
        return self.rng.choice(self.pre_response_texts)

    async def handle_text(self, text: str | None) -> dict:
        trigger_result = self.trigger.analyze(text)
        if not trigger_result["should_trigger"]:
            return {
                "handled": False,
                "reason": trigger_result["reason"],
                "trigger_result": trigger_result,
            }

        pre_response_text = self.pick_pre_response_text()
        actions = [
            await self.robot_motion.show_expression("caring"),
            await self.robot_motion.say(pre_response_text),
            await self.robot_motion.move_out_of_dock(**LOCAL_CARE_MOTION),
        ]
        return {
            "handled": True,
            "reason": "asr_emotion_triggered",
            "trigger_result": trigger_result,
            "pre_response_text": pre_response_text,
            "local_care_motion": dict(LOCAL_CARE_MOTION),
            "actions": actions,
        }
