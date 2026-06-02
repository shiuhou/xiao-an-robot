"""Xiao An Agent Brain MVP.

This module is still not an OpenClaw replacement. For the local simulation MVP,
it acts as a small event router: emotion events go to EmotionMonitorSkill, which
can use RobotGateway and EmotionDB to trigger robot care actions.
"""

from __future__ import annotations

from typing import Any

from agent.core.gateway import RobotGateway
from agent.skills.emotion_monitor import EmotionMonitorSkill
from base_station.monitor.emotion_db import EmotionDB


SUPPORTED_EMOTION_EVENTS = {"emotion.sample", "emotion.alert"}


class XiaoAnBrain:
    """Minimal Agent brain for routing local MVP events to skills."""

    def __init__(
        self,
        gateway: Any | None = None,
        memory: Any | None = None,
        gateway_url: str = "ws://127.0.0.1:8765/agent",
        db_path: str = "agent/data/xiao_an.db",
        window_seconds: int = 300,
    ):
        self.gateway = gateway or RobotGateway(url=gateway_url)
        self.memory = memory or EmotionDB(db_path=db_path)
        self.emotion_monitor = EmotionMonitorSkill(
            gateway=self.gateway,
            memory=self.memory,
            window_seconds=window_seconds,
        )

    async def handle_event(self, event: dict) -> dict:
        event_type = event.get("type")
        if event_type in SUPPORTED_EMOTION_EVENTS:
            trigger = event.get("payload") or event
            return await self.emotion_monitor.run(trigger)

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
