"""Xiao An Agent Brain MVP.

This module is still not an OpenClaw replacement. For the local simulation MVP,
it acts as a small event router: emotion events go to EmotionMonitorSkill, which
can use RobotGateway and EmotionDB to trigger robot care actions.
"""

from __future__ import annotations

from typing import Any

from agent.core.action_executor import ActionExecutor
from agent.core.gateway import RobotGateway
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawEvent
from agent.skills.companion_request import CompanionRequestSkill
from agent.skills.emotion_monitor import EmotionMonitorSkill
from agent.skills.robot_motion import RobotMotionSkill
from base_station.monitor.emotion_db import EmotionDB


SUPPORTED_EMOTION_EVENTS = {"emotion.sample", "emotion.alert"}
ASR_TRANSCRIPT_EVENT = "asr.transcript"


class XiaoAnBrain:
    """Minimal Agent brain for routing local MVP events to skills."""

    def __init__(
        self,
        gateway: Any | None = None,
        memory: Any | None = None,
        gateway_url: str = "ws://127.0.0.1:8765/agent",
        db_path: str = "agent/data/xiao_an.db",
        window_seconds: int = 300,
        openclaw_adapter: Any | None = None,
        action_executor: Any | None = None,
    ):
        self.gateway = gateway or RobotGateway(url=gateway_url)
        self.memory = memory or EmotionDB(db_path=db_path)
        self.robot_motion = RobotMotionSkill(gateway=self.gateway)
        self.emotion_monitor = EmotionMonitorSkill(
            gateway=self.gateway,
            memory=self.memory,
            window_seconds=window_seconds,
        )
        self.companion_request = CompanionRequestSkill(
            robot_motion=self.robot_motion,
        )
        self.openclaw_adapter = openclaw_adapter or FakeOpenClawAdapter()
        self.action_executor = action_executor or ActionExecutor(self.robot_motion)

    async def handle_event(self, event: dict) -> dict:
        event_type = event.get("type")
        if event_type in SUPPORTED_EMOTION_EVENTS:
            trigger = event.get("payload") or event
            return await self.emotion_monitor.run(trigger)

        if event_type == ASR_TRANSCRIPT_EVENT:
            payload = event.get("payload") or {}
            text = payload.get("text")
            companion_result = await self.companion_request.handle_text(text)
            if companion_result.get("handled", False):
                return companion_result

            openclaw_event = OpenClawEvent(
                type=ASR_TRANSCRIPT_EVENT,
                text=text,
                source="asr",
                session_id=payload.get("session_id", "default"),
                context={
                    "payload": payload,
                    "companion_result": companion_result,
                },
            )
            decision = self.openclaw_adapter.handle_event(openclaw_event)
            execution_result = await self.action_executor.execute(decision)
            execution_result["route"] = "link_1_openclaw"
            execution_result["reason"] = "openclaw_decision"
            execution_result["companion_result"] = companion_result
            return execution_result

        return {
            "handled": False,
            "reason": "unsupported_event",
            "message": f"Unsupported event type: {event_type}",
        }

    def close(self) -> None:
        close = getattr(self.memory, "close", None)
        if callable(close):
            close()


# Backward-compatible alias for older imports.
Brain = XiaoAnBrain


if __name__ == "__main__":
    print("XiaoAnBrain MVP is available. Import XiaoAnBrain and call handle_event(event).")
