"""Unit tests for XiaoAnBrain ASR transcript routing."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from agent.core.memory import XiaoAnMemoryStore
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
    def __init__(self) -> None:
        self.closed = False

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
        self.closed = True


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


class FakeHandledCompanion:
    async def handle_text(self, text: str | None) -> dict:
        return {
            "handled": True,
            "reason": "asr_emotion_triggered",
            "trigger_result": {"should_trigger": True},
        }


class RaisingOpenClawAdapter:
    def __init__(self) -> None:
        self.events = []

    def handle_event(self, event) -> OpenClawDecision:
        self.events.append(event)
        raise RuntimeError("openclaw unavailable")


class XiaoAnBrainASREventTest(unittest.IsolatedAsyncioTestCase):
    async def test_asr_transcript_tired_text_uses_companion_fast_path(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter()
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "我有点累"},
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "asr_emotion_triggered")
        self.assertTrue(result["trigger_result"]["should_trigger"])
        self.assertEqual(result["trigger_result"]["reason"], "fatigue_keyword")
        self.assertEqual(result["route"], "link_3_companion_fast_path")
        self.assertEqual(result["openclaw_event_type"], "companion.request")

    async def test_asr_transcript_companion_fast_path_records_memory_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "brain_companion_memory.db")
            with XiaoAnMemoryStore(db_path) as context_memory:
                gateway = FakeGateway()
                openclaw_adapter = FakeOpenClawAdapter(
                    decision=OpenClawDecision(handled=False),
                )
                brain = XiaoAnBrain(
                    gateway=gateway,
                    memory=FakeMemory(),
                    openclaw_adapter=openclaw_adapter,
                    context_memory=context_memory,
                )

                result = await brain.handle_event({
                    "type": "asr.transcript",
                    "payload": {
                        "text": "我有点累",
                        "session_id": "session-memory",
                        "timestamp_ms": 123456,
                    },
                })

                events = context_memory.query_recent_events(event_type="companion.request")
                care_events = context_memory.query_recent_events(event_type="robot.care_action")

                self.assertEqual(result["route"], "link_3_companion_fast_path")
                self.assertEqual(len(events), 1)
                event = events[0]
                self.assertEqual(event["source"], "brain")
                self.assertEqual(event["session_id"], "session-memory")
                self.assertEqual(event["timestamp_ms"], 123456)
                metadata = event["payload"]["metadata"]
                self.assertEqual(metadata["route"], "link_3_companion_fast_path")
                self.assertEqual(metadata["asr_text"], "我有点累")
                self.assertEqual(metadata["user_text"], "我有点累")
                self.assertEqual(metadata["reason"], "asr_emotion_triggered")
                self.assertEqual(metadata["trigger"]["reason"], "fatigue_keyword")
                self.assertEqual(metadata["matched_keyword"], "累")
                self.assertEqual(metadata["emotion_tag"], "tired")
                self.assertEqual(metadata["fatigue_score"], 0.8)
                self.assertEqual(metadata["openclaw_event_type"], "companion.request")
                self.assertTrue(metadata["handled"])
                self.assertEqual(len(care_events), 1)
                care_metadata = care_events[0]["payload"]["metadata"]
                self.assertEqual(care_metadata["route"], "link_3_companion_fast_path")
                self.assertEqual(care_metadata["source_event_type"], "companion.request")
                self.assertIn("robot_action_result", care_metadata)
                self.assertIn("care_result", care_metadata)
                self.assertIsNotNone(care_metadata["expression"])
                self.assertIsNotNone(care_metadata["motion"])
                self.assertIsNotNone(care_metadata["tts"])
                self.assertTrue(care_metadata["handled"])
                self.assertTrue(care_metadata["success"])

    async def test_asr_transcript_triggers_robot_care_sequence(self) -> None:
        gateway = FakeGateway()
        brain = XiaoAnBrain(gateway=gateway, memory=FakeMemory())

        await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "我有点累"},
        })

        self.assertEqual([call[0] for call in gateway.calls[:3]], ["expression", "motion", "tts"])
        self.assertEqual(gateway.calls[0][1], "caring")
        self.assertEqual(gateway.calls[1][1], "move_out_of_dock")

    async def test_companion_fast_path_is_forwarded_to_openclaw_for_followup(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {
                "text": "我有点累",
                "session_id": "session-3",
            },
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["route"], "link_3_companion_fast_path")
        self.assertEqual(len(openclaw_adapter.events), 1)
        openclaw_event = openclaw_adapter.events[0]
        self.assertEqual(openclaw_event.type, "companion.request")
        self.assertEqual(openclaw_event.text, "我有点累")
        self.assertEqual(openclaw_event.source, "asr")
        self.assertEqual(openclaw_event.session_id, "session-3")
        self.assertEqual(openclaw_event.context["payload"]["text"], "我有点累")
        self.assertEqual(openclaw_event.context["companion_result"]["reason"], "asr_emotion_triggered")
        self.assertEqual(openclaw_event.context["trigger_result"]["reason"], "fatigue_keyword")

    async def test_companion_fast_path_openclaw_reply_text_is_executed_as_followup(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=True, reply_text="先休息一下，我会陪着你。"),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "我有点累"},
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["route"], "link_3_companion_fast_path")
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts", "tts"])
        self.assertEqual(gateway.calls[-1][1], "先休息一下，我会陪着你。")
        self.assertEqual(result["openclaw_result"]["handled"], True)
        self.assertEqual(result["openclaw_result"]["executed_actions"][0]["source"], "reply_text")

    async def test_companion_fast_path_keeps_local_result_when_openclaw_raises(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = RaisingOpenClawAdapter()
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "我有点累"},
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "asr_emotion_triggered")
        self.assertEqual(result["route"], "link_3_companion_fast_path")
        self.assertIn("openclaw unavailable", result["openclaw_error"])
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "motion", "tts"])

    async def test_asr_transcript_normal_text_routes_to_openclaw(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=True, reply_text="weather reply"),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {
                "text": "帮我查一下天气",
                "session_id": "session-1",
            },
        })

        self.assertEqual(result["route"], "link_1_openclaw")
        self.assertEqual(result["reason"], "openclaw_decision")
        self.assertNotEqual(result["route"], "link_3_companion_fast_path")
        self.assertFalse(result["companion_result"]["handled"])
        self.assertEqual(len(openclaw_adapter.events), 1)
        openclaw_event = openclaw_adapter.events[0]
        self.assertEqual(openclaw_event.type, "asr.transcript")
        self.assertEqual(openclaw_event.text, "帮我查一下天气")
        self.assertEqual(openclaw_event.source, "asr")
        self.assertEqual(openclaw_event.session_id, "session-1")
        self.assertEqual(openclaw_event.context["payload"]["text"], "帮我查一下天气")
        self.assertEqual(openclaw_event.context["companion_result"]["reason"], "normal")

    async def test_openclaw_reply_text_is_executed_as_robot_say(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=True, reply_text="weather reply"),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "帮我查一下天气"},
        })

        self.assertEqual([call[0] for call in gateway.calls], ["tts"])
        self.assertEqual(gateway.calls[0][1], "weather reply")
        self.assertEqual(result["executed_actions"][0]["name"], "robot.say")
        self.assertEqual(result["executed_actions"][0]["source"], "reply_text")

    async def test_openclaw_normal_text_does_not_move_out_of_dock(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=True, reply_text="weather reply"),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "帮我查一下天气"},
        })

        self.assertNotIn("motion", [call[0] for call in gateway.calls])

    async def test_asr_transcript_missing_text_does_not_crash(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({"type": "asr.transcript", "payload": {}})

        self.assertFalse(result["handled"])
        self.assertEqual(result["route"], "link_1_openclaw")
        self.assertEqual(result["reason"], "openclaw_decision")
        self.assertEqual(gateway.calls, [])

    async def test_asr_transcript_weather_question_does_not_inject_work(self) -> None:
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
            "type": "asr.transcript",
            "payload": {"text": "今天天气怎么样"},
        })

        context = openclaw_adapter.events[0].context
        self.assertNotIn("work", context)
        self.assertFalse(context["context_policy"]["needs_work_context"])

    async def test_asr_transcript_work_question_injects_work(self) -> None:
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
            "type": "asr.transcript",
            "payload": {"text": "我刚刚在做什么"},
        })

        context = openclaw_adapter.events[0].context
        self.assertEqual(context["payload"]["text"], "我刚刚在做什么")
        self.assertEqual(context["work"]["recent_summary"]["latest_app_name"], "VS Code")
        self.assertEqual(context["work"]["recent_activities"][0]["activity_type"], "coding")

    async def test_asr_transcript_note_question_injects_notes(self) -> None:
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
            "type": "asr.transcript",
            "payload": {"text": "我刚刚记了什么"},
        })

        context = openclaw_adapter.events[0].context
        self.assertIn("notes", context)
        self.assertEqual(context["notes"]["recent_notes"][0]["content"], "明天下午交报告")
        self.assertNotIn("work", context)

    async def test_asr_transcript_task_question_injects_tasks(self) -> None:
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
            "type": "asr.transcript",
            "payload": {"text": "我今天还有什么任务"},
        })

        context = openclaw_adapter.events[0].context
        self.assertIn("tasks", context)
        self.assertEqual(context["tasks"]["recent_tasks"][0]["title"], "完成 Step 24")

    async def test_asr_transcript_reminder_question_injects_reminders(self) -> None:
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
            "type": "asr.transcript",
            "payload": {"text": "刚才设了什么提醒"},
        })

        context = openclaw_adapter.events[0].context
        self.assertIn("reminders", context)
        self.assertEqual(context["reminders"]["recent_reminders"][0]["message"], "休息一下")

    async def test_asr_transcript_summary_question_injects_multiple_scopes(self) -> None:
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
            "type": "asr.transcript",
            "payload": {"text": "总结一下今天进展"},
        })

        context = openclaw_adapter.events[0].context
        for scope in ("work", "notes", "tasks", "reminders", "summaries"):
            self.assertIn(scope, context)
        self.assertEqual(context["context_policy"]["method"], "keyword_heuristic")

    async def test_asr_transcript_tired_fast_path_route_is_unchanged(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter()
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
            context_memory=FakeContextMemory(),
        )
        brain.companion_request = FakeHandledCompanion()

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "鎴戞湁鐐圭疮"},
        })

        self.assertEqual(result["route"], "link_3_companion_fast_path")


if __name__ == "__main__":
    unittest.main()
