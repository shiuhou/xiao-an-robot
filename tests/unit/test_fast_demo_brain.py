from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from base_station.integration_console.fast_demo_brain import (
    OPENCLAW_DASHBOARD_SCHEMA,
    PUBLIC_LABEL,
    build_fast_demo_voice_output,
    build_reminder_due_decision,
    build_reminder_record,
    decide_visual,
    decide_voice,
    execute_robot_plan,
    iter_fast_demo_tts_texts,
    parse_reminder_due_at,
    publish_fast_demo_dashboard_capture,
)


class FastDemoBrainTest(unittest.TestCase):
    def test_fast_demo_tts_manifest_covers_all_reply_variants(self) -> None:
        items = iter_fast_demo_tts_texts()
        texts = [item["text"] for item in items]

        self.assertGreaterEqual(len(items), 58)
        self.assertEqual(len(texts), len(set(texts)))
        self.assertTrue(any(item["intent"] == "reminder_due" for item in items))
        self.assertTrue(any(item["link"] == "fast1" and item["intent"] == "capture_schedule" for item in items))
        self.assertTrue(any(item["link"] == "fast3" and item["intent"] == "set_expression" for item in items))
        self.assertTrue(any(item["variant"] == "happy" and "开心模式" in item["text"] for item in items))
        self.assertTrue(any(item["link"] == "fast3" and item["intent"] == "status_intro" for item in items))
        self.assertTrue(any(item["link"] == "fast2" and item["intent"] == "visual_normal" for item in items))
        self.assertTrue(any(item["link"] == "fast1" and item["intent"] == "recall_preference" for item in items))
        self.assertTrue(all(item["text"] for item in items))

    def test_link1_reminder_decision_uses_public_brain_label(self) -> None:
        decision = decide_voice("fast1", "小安，十分钟后提醒我喝水")

        self.assertEqual(decision["public_label"], PUBLIC_LABEL)
        self.assertEqual(decision["intent"], "capture_reminder")
        self.assertIn("reminder", decision["trigger"])
        self.assertIn("due_at", decision["trigger"]["reminder"])
        self.assertFalse(decision["robot_plan"]["allow_motion_required"])
        self.assertNotIn("本地", decision["reply_text"])

    def test_link3_care_decision_plans_conservative_motion(self) -> None:
        decision = decide_voice("fast3", "小安我有点累，出来陪我一下")

        self.assertEqual(decision["intent"], "companion_care")
        self.assertTrue(decision["robot_plan"]["allow_motion_required"])
        motion = [step for step in decision["robot_plan"]["steps"] if step["kind"] == "motion"][0]
        self.assertEqual(motion["action"], "move_out_of_dock")
        self.assertEqual(motion["params"]["distance_cm"], 8.0)
        self.assertEqual(motion["params"]["speed"], 1.0)
        self.assertEqual(motion["timeout_ms"], 1200)

    def test_link3_return_base_station_phrase_returns_to_dock(self) -> None:
        decision = decide_voice("fast3", "小安，返回基站")

        self.assertEqual(decision["intent"], "return_to_dock")
        motion = [step for step in decision["robot_plan"]["steps"] if step["kind"] == "motion"][0]
        self.assertEqual(motion["action"], "move_back_to_dock")

    def test_link3_chinese_expression_names_switch_face_without_motion(self) -> None:
        cases = {
            "小安，切换开心表情": "happy",
            "小安，换成关怀表情": "caring",
            "小安，显示疲惫脸": "tired",
            "小安，来个思考表情": "thinking",
            "小安，切换说话表情": "speaking",
            "小安，换成待命表情": "idle",
            "小安，显示难过表情": "sad",
            "小安，来个惊讶表情": "surprised",
            "小安，切换睡觉表情": "sleeping",
            "小安，装作很困": "tired",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                decision = decide_voice("fast3", text)
                self.assertEqual(decision["intent"], "set_expression")
                self.assertEqual(decision["trigger"]["expression"], expected)
                self.assertFalse(decision["robot_plan"]["allow_motion_required"])
                expression_step = decision["robot_plan"]["steps"][0]
                self.assertEqual(expression_step["expression"], expected)
                self.assertIn("tts", [step["kind"] for step in decision["robot_plan"]["steps"]])

    def test_link3_status_intro_uses_demo_preset(self) -> None:
        decision = decide_voice("fast3", "小安，你现在状态怎么样")

        self.assertEqual(decision["intent"], "status_intro")
        self.assertEqual(decision["reply_text"], "我现在电量 87%，网络正常，今天已经准备好陪你开始工作。")
        self.assertEqual(decision["robot_plan"]["steps"][0]["expression"], "speaking")
        self.assertFalse(decision["robot_plan"]["allow_motion_required"])

    def test_link3_care_phrase_still_uses_companion_care_without_expression_marker(self) -> None:
        decision = decide_voice("fast3", "小安，我有点累，出来陪我")

        self.assertEqual(decision["intent"], "companion_care")
        self.assertTrue(decision["robot_plan"]["allow_motion_required"])

    def test_link1_schedule_keyword_is_dashboard_schedule_intent(self) -> None:
        decision = decide_voice("fast1", "小安，明天下午三点把汇报加入日程")

        self.assertEqual(decision["intent"], "capture_schedule")
        self.assertIn("schedule", decision["trigger"])

    def test_link1_demo_trigger_phrases_route_to_dashboard_lists(self) -> None:
        cases = {
            "小安，把准备路演材料加入todo list": "capture_task",
            "小安，把明天下午三点做路演彩排加入日程": "capture_schedule",
            "小安，三十秒后提醒我检查摄像头": "capture_reminder",
            "小安，30秒后叫我一下喝水": "capture_reminder",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(decide_voice("fast1", text)["intent"], expected)

    def test_link1_demo_memory_questions_use_preset_replies(self) -> None:
        cases = {
            "小安记一下，我喜欢科幻故事": ("capture_preference", "preference_story", "我记住啦，你喜欢科幻故事。"),
            "小安，你记得我喜欢什么故事吗": ("recall_preference", "preference_story", "你喜欢科幻故事，所以我下次可以给你讲星际探险。"),
            "小安，你知道我是谁吗": ("recall_identity", "identity", "我知道你是小安项目的负责人，正在带我准备今天的演示。"),
            "小安，我最近在做什么": ("recall_current_work", "current_work", "你最近正在准备小安机器人的成品演示，我会帮你把提醒、日程和互动环节稳稳记住。"),
            "小安，你记得我的目标吗": ("recall_demo_goal", "demo_goal", "你希望我展示语音记忆、主动提醒、视觉关怀和具身陪伴能力。"),
        }
        for text, (intent, memory_key, reply) in cases.items():
            with self.subTest(text=text):
                decision = decide_voice("fast1", text)
                self.assertEqual(decision["intent"], intent)
                self.assertEqual(decision["reply_text"], reply)
                self.assertEqual(decision["robot_plan"]["steps"][0]["expression"], "happy" if intent == "capture_preference" else "speaking")
                self.assertEqual(decision["trigger"]["memory_key"], memory_key)

    def test_link1_demo_memory_does_not_write_dashboard_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = Path(temp_dir) / "state" / "dashboard.json"
            decision = decide_voice("fast1", "小安，你记得我喜欢什么故事吗")
            result = publish_fast_demo_dashboard_capture(
                decision,
                "小安，你记得我喜欢什么故事吗",
                dashboard_path=dashboard_path,
            )

        self.assertIsNone(result)
        self.assertFalse(dashboard_path.exists())

    def test_visual_decision_uses_gate_cv_and_vlm_signals(self) -> None:
        decision = decide_visual(
            {
                "frame_id": 17,
                "observation": {"face_detected": True},
                "cv_sample": {"emotion_tag": "neutral", "confidence": 0.4, "fatigue_score": 0.12},
                "gate": {"result": {"should_trigger": False}},
                "vlm": {"status": "done", "result": {"expression_label": "tired"}},
            }
        )

        self.assertEqual(decision["intent"], "visual_care")
        self.assertEqual(decision["trigger"]["vlm_label"], "tired")
        self.assertTrue(any(token in decision["reply_text"] for token in ("累", "疲惫", "喝口水")))

    def test_visual_low_quality_returns_uncertain_without_motion(self) -> None:
        decision = decide_visual(
            {
                "observation": {"face_detected": False},
                "cv_sample": {"observation_quality": 0.1, "fatigue_score": 0.9},
                "gate": {"result": {"should_trigger": True}},
            }
        )

        self.assertEqual(decision["intent"], "visual_uncertain")
        self.assertFalse(decision["robot_plan"]["allow_motion_required"])

    def test_build_fast_demo_voice_output_preserves_asr_event_and_merges_idea_into_note(self) -> None:
        event = {"type": "asr.transcript", "payload": {"session_id": "unit"}}
        output = build_fast_demo_voice_output("记一下这个点子", event, link="fast1")

        self.assertEqual(output["event"], event)
        self.assertEqual(output["public_label"], PUBLIC_LABEL)
        self.assertEqual(output["fast_demo_decision"]["intent"], "capture_note")
        self.assertEqual(output["reply_text"], output["fast_demo_decision"]["reply_text"])

    def test_note_triggers_include_biji_and_idea_keywords(self) -> None:
        self.assertEqual(decide_voice("fast1", "小安，这条笔记是产品想法")["intent"], "capture_note")
        self.assertEqual(decide_voice("fast1", "小安，记录一下新的灵感")["intent"], "capture_note")

    def test_parse_reminder_due_at_supports_relative_minutes(self) -> None:
        now = datetime(2026, 7, 8, 21, 30, tzinfo=timezone.utc)
        reminder = parse_reminder_due_at("小安，三分钟后提醒我喝水", now=now)

        self.assertEqual(reminder["delay_seconds"], 180)
        self.assertEqual(reminder["time_text"], "三分钟后")

    def test_reminder_record_and_due_decision_plan_move_out(self) -> None:
        decision = decide_voice("fast1", "小安，10秒后提醒我喝水")
        record = build_reminder_record(
            decision,
            transcript="小安，10秒后提醒我喝水",
            send_to_robot=True,
            allow_motion=True,
            gateway_url="ws://127.0.0.1:8765/agent",
            now=datetime(2026, 7, 8, 21, 30, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(record)
        due_decision = build_reminder_due_decision(record or {})
        self.assertEqual(due_decision["intent"], "reminder_due")
        self.assertTrue(due_decision["robot_plan"]["allow_motion_required"])
        motion = [step for step in due_decision["robot_plan"]["steps"] if step["kind"] == "motion"][0]
        self.assertEqual(motion["action"], "move_out_of_dock")
        self.assertEqual(motion["params"]["distance_cm"], 8.0)

    def test_publish_fast_demo_dashboard_capture_writes_todo_schedule_and_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = Path(temp_dir) / "state" / "dashboard.json"

            task = decide_voice("fast1", "小安，把整理材料加入todo list")
            task_result = publish_fast_demo_dashboard_capture(
                task,
                "小安，把整理材料加入todo list",
                dashboard_path=dashboard_path,
                now=datetime(2026, 7, 9, 19, 30, tzinfo=timezone.utc),
            )
            schedule = decide_voice("fast1", "小安，明天下午三点把汇报加入日程")
            schedule_result = publish_fast_demo_dashboard_capture(
                schedule,
                "小安，明天下午三点把汇报加入日程",
                dashboard_path=dashboard_path,
                now=datetime(2026, 7, 9, 19, 31, tzinfo=timezone.utc),
            )
            reminder = decide_voice("fast1", "小安，三分钟后提醒我喝水")
            reminder_result = publish_fast_demo_dashboard_capture(
                reminder,
                "小安，三分钟后提醒我喝水",
                dashboard_path=dashboard_path,
                now=datetime(2026, 7, 9, 19, 32, tzinfo=timezone.utc),
            )

            data = json.loads(dashboard_path.read_text(encoding="utf-8"))

        self.assertEqual(task_result["list"], "todos")
        self.assertEqual(schedule_result["list"], "schedules")
        self.assertEqual(reminder_result["list"], "reminders")
        self.assertEqual(data["schema"], OPENCLAW_DASHBOARD_SCHEMA)
        self.assertEqual(data["todos"][0]["title"], "整理材料")
        self.assertEqual(data["schedules"][0]["title"], "汇报")
        self.assertEqual(data["schedules"][0]["time"], "15:00")
        self.assertEqual(data["reminders"][0]["title"], "喝水")
        self.assertEqual(data["latest_reply"]["source"], "fast_link1")

    def test_execute_robot_plan_skips_motion_when_disabled(self) -> None:
        decision = decide_voice("fast3", "出来陪我")

        with patch("base_station.integration_console.fast_demo_brain.RobotGateway") as gateway_class:
            gateway = gateway_class.return_value
            gateway.send_expression = AsyncMock(return_value={"type": "agent.ack", "payload": {"ok": True}})
            gateway.send_motion = AsyncMock(return_value={"type": "agent.ack", "payload": {"ok": True}})
            gateway.send_tts = AsyncMock(return_value={"type": "agent.ack", "payload": {"ok": True}})
            result = asyncio.run(
                execute_robot_plan(
                    decision,
                    gateway_url="ws://127.0.0.1:8765/agent",
                    send_to_robot=True,
                    allow_motion=False,
                )
            )

        self.assertTrue(result["ok"])
        self.assertTrue(any(item["reason"] == "motion_disabled" for item in result["skipped_actions"]))
        gateway.send_motion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
