"""Unit tests for XiaoAnBrain frontend.message routing."""

from __future__ import annotations

import unittest

from agent.core.brain import XiaoAnBrain
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    async def send_expression(self, expression: str, duration_ms: int = 3000, loop: bool = False) -> dict:
        self.calls.append(("expression", expression, duration_ms, loop))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "display.expression"}}

    async def send_motion(self, action: str, params: dict | None = None, timeout_ms: int = 5000) -> dict:
        self.calls.append(("motion", action, params or {}, timeout_ms))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "motion.execute"}}

    async def send_tts(self, text: str) -> dict:
        self.calls.append(("tts", text))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "audio.play_tts"}}


class FakeMemory:
    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        timestamp: int | None = None,
    ) -> int:
        return 1

    def get_recent_summary(self, seconds: int = 300, now_ms: int | None = None) -> dict:
        return {
            "count": 0,
            "avg_fatigue_score": 0.0,
            "max_confidence": 0.0,
            "top_emotion": None,
            "emotions_count": {},
        }

    def close(self) -> None:
        pass


class XiaoAnBrainFrontendEventTest(unittest.IsolatedAsyncioTestCase):
    async def test_frontend_message_routes_to_openclaw_adapter(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=True, reply_text="你好，我在。"),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "frontend.message",
            "payload": {
                "text": "你好小安",
                "session_id": "frontend-session-1",
            },
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "openclaw_decision")
        self.assertEqual(result["route"], "frontend_openclaw")
        self.assertEqual(result["reply_text"], "你好，我在。")
        self.assertEqual(len(openclaw_adapter.events), 1)
        openclaw_event = openclaw_adapter.events[0]
        self.assertEqual(openclaw_event.type, "frontend.message")
        self.assertEqual(openclaw_event.text, "你好小安")
        self.assertEqual(openclaw_event.source, "frontend")
        self.assertEqual(openclaw_event.session_id, "frontend-session-1")
        self.assertEqual(openclaw_event.context["payload"]["text"], "你好小安")

    async def test_frontend_message_does_not_use_companion_fast_path(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=True, reply_text="交给 OpenClaw 处理。"),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "我有点累"},
        })

        self.assertEqual(result["route"], "frontend_openclaw")
        self.assertEqual(result["reason"], "openclaw_decision")
        self.assertEqual(openclaw_adapter.events[0].text, "我有点累")
        self.assertEqual([call[0] for call in gateway.calls], ["tts"])
        self.assertNotIn("motion", [call[0] for call in gateway.calls])

    async def test_openclaw_reply_text_is_executed_as_robot_say(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=True, reply_text="frontend reply"),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "生成今天总结"},
        })

        self.assertEqual([call[0] for call in gateway.calls], ["tts"])
        self.assertEqual(gateway.calls[0][1], "frontend reply")
        self.assertEqual(result["executed_actions"][0]["name"], "robot.say")
        self.assertEqual(result["executed_actions"][0]["source"], "reply_text")

    async def test_frontend_message_defaults_session_id(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "随便聊聊"},
        })

        self.assertFalse(result["handled"])
        self.assertEqual(result["route"], "frontend_openclaw")
        self.assertEqual(result["reason"], "openclaw_decision")
        self.assertEqual(openclaw_adapter.events[0].session_id, "default")


if __name__ == "__main__":
    unittest.main()
