"""Unit tests for optional EmotionDB mirroring into memory_events."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore
from base_station.monitor.emotion_db import EmotionDB


class FailingMemoryStore:
    def insert_event(self, **kwargs: object) -> int:
        raise RuntimeError("memory mirror failed")


class EmotionMemoryBridgeTest(unittest.TestCase):
    def emotion_db_path(self, temp_dir: str) -> str:
        return str(Path(temp_dir) / "emotions.db")

    def memory_db_path(self, temp_dir: str) -> str:
        return str(Path(temp_dir) / "memory.db")

    def test_without_memory_store_keeps_old_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with EmotionDB(self.emotion_db_path(temp_dir)) as db:
                row_id = db.insert_emotion(
                    "face",
                    "neutral",
                    0.8,
                    0.3,
                    timestamp=2_000_000,
                )

                rows = db.query_recent(seconds=300, now_ms=2_001_000)

                self.assertIsInstance(row_id, int)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["emotion_tag"], "neutral")

    def test_mirror_writes_emotions_and_memory_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.memory_db_path(temp_dir)) as memory_store:
                with EmotionDB(
                    self.emotion_db_path(temp_dir),
                    memory_store=memory_store,
                    mirror_to_memory=True,
                ) as db:
                    row_id = db.insert_emotion(
                        "face",
                        "tired",
                        0.9,
                        0.7,
                        timestamp=2_000_000,
                    )

                    emotion_rows = db.query_recent(seconds=300, now_ms=2_001_000)
                    events = memory_store.query_recent_events(event_type="emotion.sample")

                    self.assertEqual(len(emotion_rows), 1)
                    self.assertEqual(emotion_rows[0]["id"], row_id)
                    self.assertEqual(len(events), 1)

    def test_memory_event_uses_emotion_sample_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.memory_db_path(temp_dir)) as memory_store:
                with EmotionDB(
                    self.emotion_db_path(temp_dir),
                    memory_store=memory_store,
                    mirror_to_memory=True,
                ) as db:
                    db.insert_emotion("voice", "anxious", 0.6, 0.4)

                    events = memory_store.query_recent_events()

                    self.assertEqual(events[0]["event_type"], "emotion.sample")

    def test_memory_event_payload_contains_emotion_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.memory_db_path(temp_dir)) as memory_store:
                with EmotionDB(
                    self.emotion_db_path(temp_dir),
                    memory_store=memory_store,
                    mirror_to_memory=True,
                ) as db:
                    row_id = db.insert_emotion("face", "sad", 0.75, 0.2)

                    payload = memory_store.query_recent_events()[0]["payload"]

                    self.assertEqual(payload["emotion_tag"], "sad")
                    self.assertEqual(payload["confidence"], 0.75)
                    self.assertEqual(payload["fatigue_score"], 0.2)
                    self.assertEqual(payload["emotion_row_id"], row_id)

    def test_mirror_false_does_not_write_memory_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.memory_db_path(temp_dir)) as memory_store:
                with EmotionDB(
                    self.emotion_db_path(temp_dir),
                    memory_store=memory_store,
                    mirror_to_memory=False,
                ) as db:
                    db.insert_emotion("face", "neutral", 0.8, 0.1)

                    events = memory_store.query_recent_events()

                    self.assertEqual(events, [])

    def test_memory_store_failure_does_not_fail_insert_emotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with EmotionDB(
                self.emotion_db_path(temp_dir),
                memory_store=FailingMemoryStore(),
                mirror_to_memory=True,
            ) as db:
                row_id = db.insert_emotion(
                    "face",
                    "tired",
                    0.9,
                    0.6,
                    timestamp=2_000_000,
                )

                rows = db.query_recent(seconds=300, now_ms=2_001_000)

                self.assertIsInstance(row_id, int)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["emotion_tag"], "tired")


if __name__ == "__main__":
    unittest.main()
