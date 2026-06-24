"""Unit tests for MemoryRecorder."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore
from agent.core.memory_recorder import MemoryRecorder


class MemoryRecorderTest(unittest.TestCase):
    def make_db_path(self, temp_dir: str) -> str:
        return str(Path(temp_dir) / "memory_recorder.db")

    def test_uses_tempfile_database_instead_of_default_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self.make_db_path(temp_dir)
            with XiaoAnMemoryStore(db_path) as db:
                recorder = MemoryRecorder(memory_store=db)

                event_id = recorder.record_companion_request(
                    asr_text="我有点累",
                    route="link_3_companion_fast_path",
                    timestamp_ms=1000,
                )

                self.assertIsInstance(event_id, int)
                self.assertEqual(db.db_path, db_path)
                self.assertNotEqual(db.db_path, str(XiaoAnMemoryStore._default_db_path()))

    def test_record_companion_request_writes_memory_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                recorder = MemoryRecorder(memory_store=db)

                event_id = recorder.record_companion_request(
                    asr_text="我有点累",
                    reply_text="先休息一下",
                    route="link_3_companion_fast_path",
                    trigger={"reason": "fatigue_keyword"},
                    session_id="s1",
                    timestamp_ms=1000,
                )

                event = db.get_event(event_id)
                self.assertIsNotNone(event)
                self.assertEqual(event["event_type"], "companion.request")
                self.assertEqual(event["source"], "companion_request")
                self.assertEqual(event["session_id"], "s1")
                self.assertEqual(event["text"], "先休息一下")
                metadata = event["payload"]["metadata"]
                self.assertEqual(metadata["route"], "link_3_companion_fast_path")
                self.assertEqual(metadata["trigger"]["reason"], "fatigue_keyword")
                self.assertEqual(metadata["asr_text"], "我有点累")
                self.assertEqual(metadata["reply_text"], "先休息一下")

    def test_record_emotion_intervention_keeps_emotion_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                recorder = MemoryRecorder(memory_store=db)

                event_id = recorder.record_emotion_intervention(
                    emotion_tag="tired",
                    confidence=0.91,
                    fatigue_score=0.82,
                    route="link_2_emotion_fast_path",
                    trigger={"source": "face"},
                    reply_text="我来陪你休息一下",
                    timestamp_ms=2000,
                )

                event = db.get_event(event_id)
                self.assertIsNotNone(event)
                self.assertEqual(event["event_type"], "emotion.intervention")
                self.assertIn("emotion=tired", event["text"])
                metadata = event["payload"]["metadata"]
                self.assertEqual(metadata["emotion_tag"], "tired")
                self.assertEqual(metadata["confidence"], 0.91)
                self.assertEqual(metadata["fatigue_score"], 0.82)
                self.assertEqual(metadata["route"], "link_2_emotion_fast_path")
                self.assertEqual(metadata["reply_text"], "我来陪你休息一下")

    def test_record_robot_care_action_keeps_action_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                recorder = MemoryRecorder(memory_store=db)

                event_id = recorder.record_robot_care_action(
                    action_name="robot.say",
                    robot_action_result={"ok": True, "forwarded_type": "audio.play_tts"},
                    route="link_3_companion_fast_path",
                    emotion_tag="tired",
                    timestamp_ms=3000,
                )

                event = db.get_event(event_id)
                self.assertIsNotNone(event)
                self.assertEqual(event["event_type"], "robot.care_action")
                self.assertEqual(event["source"], "robot_care")
                self.assertEqual(event["text"], "robot.say")
                metadata = event["payload"]["metadata"]
                self.assertEqual(metadata["action_name"], "robot.say")
                self.assertEqual(metadata["robot_action_result"]["ok"], True)
                self.assertEqual(metadata["robot_action_result"]["forwarded_type"], "audio.play_tts")
                self.assertEqual(metadata["emotion_tag"], "tired")

    def test_non_json_metadata_is_stringified(self) -> None:
        class CustomValue:
            def __str__(self) -> str:
                return "custom-value"

        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                recorder = MemoryRecorder(memory_store=db)

                event_id = recorder.record_robot_care_action(
                    action_name="robot.expression",
                    metadata={"custom": CustomValue()},
                )

                event = db.get_event(event_id)
                self.assertIsNotNone(event)
                self.assertEqual(event["payload"]["metadata"]["custom"], "custom-value")


if __name__ == "__main__":
    unittest.main()
