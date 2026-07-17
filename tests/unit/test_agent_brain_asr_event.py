"""Unit tests for XiaoAnBrain ASR transcript routing."""

from __future__ import annotations

import unittest
import tempfile
import json
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from agent.core.local_fast_path import LocalFastPathRouter
from agent.core.memory import XiaoAnMemoryStore
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision
from agent.core.runtime_workspace_docs import RuntimeWorkspaceDocs
from agent.core.work_mode import WorkModeStore
from agent.skills.companion_request import LOCAL_CARE_MOTION, PRE_RESPONSE_TEXTS


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


class SnapshotOpenClawAdapter:
    def __init__(self, gateway: FakeGateway, decision: OpenClawDecision | None = None) -> None:
        self.gateway = gateway
        self.decision = decision or OpenClawDecision(handled=False)
        self.events = []
        self.calls_seen_before_openclaw = []

    def handle_event(self, event) -> OpenClawDecision:
        self.events.append(event)
        self.calls_seen_before_openclaw = list(self.gateway.calls)
        return self.decision


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

    async def test_asr_transcript_can_disable_companion_fast_path(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter()
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {
                "text": "我有点累",
                "disable_companion_fast_path": True,
            },
        })

        self.assertEqual(result["route"], "link_1_openclaw")
        self.assertEqual(result["companion_result"]["reason"], "companion_fast_path_disabled")
        self.assertNotIn(("expression", "caring", 3000, False), gateway.calls)
        self.assertFalse(any(call[0] == "move" for call in gateway.calls))
        self.assertEqual(openclaw_adapter.events[0].type, "asr.transcript")

    async def test_asr_task_uses_local_fast_path_and_writes_runtime_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace-xiaoan-runtime"
            openclaw_adapter = FakeOpenClawAdapter()
            brain = XiaoAnBrain(
                gateway=FakeGateway(),
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                local_fast_path=LocalFastPathRouter(RuntimeWorkspaceDocs(workspace)),
                work_mode_store=WorkModeStore(root / "work_mode.json", cooldown_seconds=0),
            )

            result = await brain.handle_event({
                "type": "asr.transcript",
                "payload": {"text": "小安，帮我加个待办，测试总工作模式"},
            })

            tasks_text = (workspace / "TASKS.md").read_text(encoding="utf-8")

        self.assertEqual(result["route"], "local_fast_path.link1.task_add")
        self.assertEqual(openclaw_adapter.events, [])
        self.assertIn("- [ ] 测试总工作模式", tasks_text)
        self.assertIn("source: local_fast_path", tasks_text)

    async def test_asr_link1_local_fast_path_task_schedule_and_reminder_crud(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace-xiaoan-runtime"
            openclaw_adapter = FakeOpenClawAdapter()
            brain = XiaoAnBrain(
                gateway=FakeGateway(),
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                local_fast_path=LocalFastPathRouter(RuntimeWorkspaceDocs(workspace)),
                work_mode_store=WorkModeStore(root / "work_mode.json", cooldown_seconds=0),
            )

            cases = [
                ("小安，帮我加个待办，测试总工作模式", "local_fast_path.link1.task_add"),
                ("查询待办", "local_fast_path.link1.task_query"),
                ("完成待办测试总工作模式", "local_fast_path.link1.task_complete"),
                ("小安，帮我加个待办，取消用例", "local_fast_path.link1.task_add"),
                ("取消待办取消用例", "local_fast_path.link1.task_cancel"),
                ("今天晚上十一点新增日程，检查总工作模式", "local_fast_path.link1.schedule_add"),
                ("查询今日日程", "local_fast_path.link1.schedule_query"),
                ("十分钟后提醒我喝水", "local_fast_path.link1.reminder_add"),
                ("查询提醒", "local_fast_path.link1.reminder_query"),
                ("取消喝水提醒", "local_fast_path.link1.reminder_cancel"),
            ]
            routes = []
            for text, _route in cases:
                result = await brain.handle_event({
                    "type": "asr.transcript",
                    "payload": {"text": text},
                })
                routes.append(result["route"])

            tasks_text = (workspace / "TASKS.md").read_text(encoding="utf-8")
            schedule_text = (workspace / "SCHEDULE.md").read_text(encoding="utf-8")
            reminders = json.loads((workspace / "state" / "local_reminders.json").read_text(encoding="utf-8"))
            dashboard = json.loads((workspace / "state" / "dashboard.json").read_text(encoding="utf-8"))

        self.assertEqual(routes, [route for _text, route in cases])
        self.assertEqual(openclaw_adapter.events, [])
        self.assertIn("- [x] 测试总工作模式", tasks_text)
        self.assertIn("cancelled_source: local_fast_path", tasks_text)
        self.assertIn("检查总工作模式", schedule_text)
        self.assertIn("scheduler: local", schedule_text)
        self.assertEqual(reminders["items"][0]["status"], "cancelled")
        self.assertEqual(dashboard["local_fast_path"]["last_route"], "local_fast_path.link1.reminder_cancel")

    async def test_asr_link3_local_fast_path_covers_robot_commands_without_openclaw(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace-xiaoan-runtime"
            openclaw_adapter = FakeOpenClawAdapter()
            gateway = FakeGateway()
            brain = XiaoAnBrain(
                gateway=gateway,
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                local_fast_path=LocalFastPathRouter(RuntimeWorkspaceDocs(workspace)),
                work_mode_store=WorkModeStore(root / "work_mode.json", cooldown_seconds=0),
            )

            cases = [
                ("停止", "local_fast_path.link3.stop_motion"),
                ("出来", "local_fast_path.link3.move_out"),
                ("回 Dock", "local_fast_path.link3.return_to_dock"),
                ("左转", "local_fast_path.link3.turn_left"),
                ("右转", "local_fast_path.link3.turn_right"),
                ("换成开心表情", "local_fast_path.link3.set_expression"),
                ("查询机器人状态", "local_fast_path.link3.robot_status"),
                ("带我呼吸", "local_fast_path.link3.breathing_guide"),
                ("小安在吗", "local_fast_path.link3.greeting"),
            ]
            routes = []
            for text, _route in cases:
                result = await brain.handle_event({
                    "type": "asr.transcript",
                    "payload": {"text": text},
                })
                routes.append(result["route"])

        self.assertEqual(routes, [route for _text, route in cases])
        self.assertEqual(openclaw_adapter.events, [])
        self.assertIn(("motion", "stop", {}, 5000), gateway.calls)
        self.assertTrue(any(call[0] == "expression" and call[1] == "happy" for call in gateway.calls))

    async def test_asr_weather_stays_on_openclaw_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            openclaw_adapter = FakeOpenClawAdapter()
            brain = XiaoAnBrain(
                gateway=FakeGateway(),
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                work_mode_store=WorkModeStore(Path(temp_dir) / "work_mode.json", cooldown_seconds=0),
            )

            result = await brain.handle_event({
                "type": "asr.transcript",
                "payload": {"text": "小安，今天会不会下雨"},
            })

        self.assertEqual(result["route"], "link_1_openclaw")
        self.assertEqual(openclaw_adapter.events[0].type, "asr.transcript")
        self.assertEqual(openclaw_adapter.events[0].context["local_fast_path"]["reason"], "openclaw_owned_intent")

    async def test_asr_notes_and_context_dependent_requests_stay_on_openclaw_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            openclaw_adapter = FakeOpenClawAdapter()
            brain = XiaoAnBrain(
                gateway=FakeGateway(),
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                work_mode_store=WorkModeStore(Path(temp_dir) / "work_mode.json", cooldown_seconds=0),
            )

            for text in ("查询笔记里有什么", "帮我规划一下今天", "像上次一样处理那个"):
                result = await brain.handle_event({
                    "type": "asr.transcript",
                    "payload": {"text": text},
                })
                self.assertEqual(result["route"], "link_1_openclaw")

        self.assertEqual(len(openclaw_adapter.events), 3)

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

        self.assertEqual([call[0] for call in gateway.calls[:3]], ["expression", "tts", "motion"])
        self.assertEqual(gateway.calls[0][1], "caring")
        self.assertIn(gateway.calls[1][1], PRE_RESPONSE_TEXTS)
        self.assertEqual(gateway.calls[2][1], "move_out_of_dock")
        self.assertEqual(gateway.calls[2][2]["speed"], LOCAL_CARE_MOTION["speed"])
        self.assertEqual(gateway.calls[2][2]["distance_cm"], float(LOCAL_CARE_MOTION["distance_cm"]))
        self.assertEqual(gateway.calls[2][2]["duration_ms"], 2200)
        self.assertEqual(gateway.calls[2][3], LOCAL_CARE_MOTION["timeout_ms"])

    async def test_companion_fast_path_pre_response_runs_before_openclaw(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = SnapshotOpenClawAdapter(gateway)
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "陪陪我"},
        })

        self.assertEqual(
            [call[0] for call in openclaw_adapter.calls_seen_before_openclaw],
            ["expression", "tts", "motion"],
        )

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
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "tts", "motion", "tts"])
        self.assertIn(gateway.calls[1][1], PRE_RESPONSE_TEXTS)
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
        self.assertEqual([call[0] for call in gateway.calls], ["expression", "tts", "motion"])

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
        self.assertEqual(openclaw_event.context["tool_profile"], "conversation")
        self.assertEqual(openclaw_event.context["route_hint"]["kind"], "conversation")

    async def test_asr_transcript_openclaw_context_omits_audio_debug_payload(self) -> None:
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(handled=False),
        )
        brain = XiaoAnBrain(
            gateway=FakeGateway(),
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        await brain.handle_event({
            "type": "asr.transcript",
            "payload": {
                "text": "帮我查一下天气",
                "source": "local_mic",
                "session_id": "mic-session",
                "timestamp_ms": 123,
                "vad": {"speech_detected": True},
                "asr": {"backend": "sensevoice"},
                "audio": {
                    "audio_path": "runtime/voice.wav",
                    "speech_trim": {"path": "runtime/voice.trim.wav"},
                },
            },
        })

        context = openclaw_adapter.events[0].context
        payload = context["payload"]
        self.assertEqual(payload["text"], "帮我查一下天气")
        self.assertEqual(payload["source"], "local_mic")
        self.assertEqual(payload["session_id"], "mic-session")
        self.assertEqual(payload["timestamp_ms"], 123)
        self.assertNotIn("vad", payload)
        self.assertNotIn("asr", payload)
        self.assertNotIn("audio", payload)
        self.assertEqual(context["tool_profile"], "conversation")
        self.assertEqual(context["local_fast_path"]["reason"], "openclaw_owned_intent")

    async def test_asr_transcript_expression_action_uses_local_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace-xiaoan-runtime"
            gateway = FakeGateway()
            openclaw_adapter = FakeOpenClawAdapter(
                decision=OpenClawDecision(handled=False),
            )
            brain = XiaoAnBrain(
                gateway=gateway,
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                local_fast_path=LocalFastPathRouter(RuntimeWorkspaceDocs(workspace)),
                work_mode_store=WorkModeStore(root / "work_mode.json", cooldown_seconds=0),
            )

            result = await brain.handle_event({
                "type": "asr.transcript",
                "payload": {"text": "小安笑一个"},
            })

        self.assertEqual(result["route"], "local_fast_path.link3.set_expression")
        self.assertEqual(openclaw_adapter.events, [])
        self.assertTrue(any(call[0] == "expression" and call[1] == "happy" for call in gateway.calls))

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

    async def test_failed_openclaw_reminder_uses_local_fallback_before_tts(self) -> None:
        gateway = FakeGateway()
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(
                handled=True,
                display_text="需要定时提醒能力才能创建 1 分钟后的提醒；当前事件没有提供可用工具。",
                spoken_text="我先记到这里，但现在还不能真正定时提醒你。",
                reply_text="需要定时提醒能力才能创建 1 分钟后的提醒；当前事件没有提供可用工具。",
                raw={
                    "handled": True,
                    "capture": {
                        "status": "failed",
                        "kind": "reminder",
                        "source_of_truth": "openclaw_xiaoan_runtime",
                        "title": "喝水",
                        "content": "1 分钟后提醒喝水。",
                        "missing_fields": ["cron_tool"],
                    },
                },
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace-xiaoan-runtime"
            brain = XiaoAnBrain(
                gateway=gateway,
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                local_fast_path=LocalFastPathRouter(RuntimeWorkspaceDocs(workspace)),
                work_mode_store=WorkModeStore(root / "work_mode.json", cooldown_seconds=0),
            )

            result = await brain.handle_event({
                "type": "asr.transcript",
                "payload": {"text": "小安，一分钟后提醒我喝水。"},
            })
            schedule_text = (workspace / "SCHEDULE.md").read_text(encoding="utf-8")

        self.assertEqual(result["route"], "local_fast_path.link1.reminder_add")
        self.assertEqual(openclaw_adapter.events, [])
        self.assertEqual(gateway.calls, [])
        self.assertIn("喝水", schedule_text)
        self.assertIn("scheduler: local", schedule_text)

    async def test_failed_openclaw_reminder_without_time_does_not_default_to_one_minute(self) -> None:
        gateway = FakeGateway()
        failure_text = "需要具体提醒时间才能创建提醒。"
        openclaw_adapter = FakeOpenClawAdapter(
            decision=OpenClawDecision(
                handled=True,
                display_text=failure_text,
                spoken_text=failure_text,
                reply_text=failure_text,
                raw={
                    "handled": True,
                    "capture": {
                        "status": "failed",
                        "kind": "reminder",
                        "title": "喝水",
                        "missing_fields": ["cron_tool"],
                    },
                },
            ),
        )
        brain = XiaoAnBrain(
            gateway=gateway,
            memory=FakeMemory(),
            openclaw_adapter=openclaw_adapter,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "小安提醒我喝水。"},
        })

        self.assertEqual(gateway.calls[0][1], failure_text)
        capture = result["openclaw_raw"]["capture"]
        self.assertEqual(capture["status"], "failed")
        self.assertNotIn("due_at", capture)

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
