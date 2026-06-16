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


class FakeContextMemory:
    def get_recent_work_summary(self, limit: int = 20) -> dict:
        return {
            "count": 3,
            "latest_activity_type": "coding",
            "latest_app_name": "VS Code",
            "latest_project_hint": "xiao-an-robot",
            "top_activity_type": "coding",
            "top_app_name": "VS Code",
            "activity_type_count": {"coding": 3},
            "app_count": {"VS Code": 3},
            "project_hint_count": {"xiao-an-robot": 3},
        }

    def query_recent_work_activities(self, limit: int = 5) -> list[dict]:
        return [{
            "app_name": "VS Code",
            "activity_type": "coding",
            "project_hint": "xiao-an-robot",
        }]

    def get_notes_summary(self, limit: int = 20) -> dict:
        return {"count": 1, "latest_content": "明天下午交报告"}

    def query_recent_notes(self, limit: int = 5) -> list[dict]:
        return [{"content": "明天下午交报告", "tags": ["work_context"]}]

    def get_tasks_summary(self, limit: int = 20) -> dict:
        return {"count": 2, "pending_count": 1, "done_count": 1}

    def query_tasks(self, limit: int = 10, include_done: bool = False) -> list[dict]:
        return [
            {"title": "完成 Step 24", "status": "pending"},
            {"title": "完成 Step 23.5", "status": "done"},
        ]

    def get_reminders_summary(self, limit: int = 20) -> dict:
        return {"count": 1, "pending_count": 1, "fired_count": 0}

    def query_reminders(self, limit: int = 10, include_fired: bool = False) -> list[dict]:
        return [{"message": "休息一下", "status": "pending"}]

    def get_summary_overview(self, limit: int = 20) -> dict:
        return {"count": 1, "latest_summary_type": "daily", "latest_title": "小安日报"}

    def query_recent_summaries(self, limit: int = 5) -> list[dict]:
        return [{"summary_type": "daily", "title": "小安日报"}]


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

    async def test_frontend_message_greeting_does_not_inject_work(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
            context_memory=FakeContextMemory(),
        )

        await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "你好小安"},
        })

        context = openclaw_adapter.events[0].context
        self.assertNotIn("work", context)
        self.assertNotIn("notes", context)
        self.assertNotIn("tasks", context)
        self.assertNotIn("reminders", context)
        self.assertNotIn("summaries", context)
        self.assertFalse(context["context_policy"]["needs_work_context"])

    async def test_frontend_message_work_question_injects_work(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
            context_memory=FakeContextMemory(),
        )

        await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "我刚刚在做什么"},
        })

        context = openclaw_adapter.events[0].context
        self.assertEqual(context["payload"]["text"], "我刚刚在做什么")
        self.assertEqual(context["work"]["recent_summary"]["latest_activity_type"], "coding")
        self.assertEqual(context["work"]["recent_activities"][0]["app_name"], "VS Code")


    async def test_frontend_message_note_question_injects_notes(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
            context_memory=FakeContextMemory(),
        )

        await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "我刚刚记了什么"},
        })

        context = openclaw_adapter.events[0].context
        self.assertIn("notes", context)
        self.assertEqual(context["notes"]["recent_notes"][0]["content"], "明天下午交报告")
        self.assertNotIn("work", context)

    async def test_frontend_message_task_question_injects_tasks(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
            context_memory=FakeContextMemory(),
        )

        await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "我今天还有什么任务"},
        })

        context = openclaw_adapter.events[0].context
        self.assertIn("tasks", context)
        self.assertEqual(context["tasks"]["recent_tasks"][0]["title"], "完成 Step 24")

    async def test_frontend_message_reminder_question_injects_reminders(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
            context_memory=FakeContextMemory(),
        )

        await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "刚才设了什么提醒"},
        })

        context = openclaw_adapter.events[0].context
        self.assertIn("reminders", context)
        self.assertEqual(context["reminders"]["recent_reminders"][0]["message"], "休息一下")


if __name__ == "__main__":
    unittest.main()
