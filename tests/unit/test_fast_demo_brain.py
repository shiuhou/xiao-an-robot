from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, patch

from base_station.integration_console.fast_demo_brain import (
    PUBLIC_LABEL,
    build_fast_demo_voice_output,
    build_reminder_due_decision,
    build_reminder_record,
    decide_visual,
    decide_voice,
    execute_robot_plan,
    iter_fast_demo_tts_texts,
    parse_reminder_due_at,
)


class FastDemoBrainTest(unittest.TestCase):
    def test_fast_demo_tts_manifest_covers_all_reply_variants(self) -> None:
        items = iter_fast_demo_tts_texts()
        texts = [item["text"] for item in items]

        self.assertEqual(len(items), 42)
        self.assertEqual(len(texts), len(set(texts)))
        self.assertTrue(any(item["intent"] == "reminder_due" for item in items))
        self.assertTrue(any(item["link"] == "fast2" and item["intent"] == "visual_normal" for item in items))
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
        self.assertEqual(motion["params"]["speed"], 0.56)
        self.assertEqual(motion["timeout_ms"], 1200)

    def test_link3_return_base_station_phrase_returns_to_dock(self) -> None:
        decision = decide_voice("fast3", "小安，返回基站")

        self.assertEqual(decision["intent"], "return_to_dock")
        motion = [step for step in decision["robot_plan"]["steps"] if step["kind"] == "motion"][0]
        self.assertEqual(motion["action"], "move_back_to_dock")

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
