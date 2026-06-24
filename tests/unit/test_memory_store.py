"""Unit tests for the unified Xiao An memory store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import Memory, XiaoAnMemoryStore


class XiaoAnMemoryStoreTest(unittest.TestCase):
    def make_db_path(self, temp_dir: str) -> str:
        return str(Path(temp_dir) / "memory_store.db")

    def table_exists(self, db: XiaoAnMemoryStore, table_name: str) -> bool:
        row = db.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def test_uses_tempfile_database_instead_of_default_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self.make_db_path(temp_dir)
            with XiaoAnMemoryStore(db_path) as db:
                default_path = str(XiaoAnMemoryStore._default_db_path())

                self.assertEqual(db.db_path, db_path)
                self.assertNotEqual(db.db_path, default_path)

    def test_initialization_creates_memory_events_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                self.assertTrue(self.table_exists(db, "memory_events"))

    def test_insert_event_returns_integer_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                event_id = db.insert_event("note", payload={"mood": "calm"})

                self.assertIsInstance(event_id, int)

    def test_query_recent_events_parses_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_event("note", source="unit", text="hello", payload={"score": 7})

                rows = db.query_recent_events()

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["text"], "hello")
                self.assertEqual(rows[0]["payload"], {"score": 7})
                self.assertIn("payload_json", rows[0])

    def test_query_recent_events_filters_by_event_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_event("note", source="unit")
                db.insert_event("task", source="unit")

                rows = db.query_recent_events(event_type="task")

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["event_type"], "task")

    def test_query_recent_events_filters_by_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_event("note", source="unit")
                db.insert_event("note", source="other")

                rows = db.query_recent_events(source="other")

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["source"], "other")

    def test_get_event_returns_requested_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                event_id = db.insert_event("note", source="unit", payload={"ok": True})

                row = db.get_event(event_id)

                self.assertIsNotNone(row)
                self.assertEqual(row["id"], event_id)
                self.assertEqual(row["payload"], {"ok": True})

    def test_save_interaction_writes_interactions_and_memory_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                interaction_id = db.save_interaction(
                    "hi",
                    "hello",
                    emotion_tag="neutral",
                    skill_called="chat",
                )

                interaction = db.conn.execute(
                    "SELECT * FROM interactions WHERE id = ?",
                    (interaction_id,),
                ).fetchone()
                events = db.query_recent_events(event_type="interaction")

                self.assertIsInstance(interaction_id, int)
                self.assertIsNotNone(interaction)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["payload"]["user_text"], "hi")
                self.assertEqual(events[0]["payload"]["reply"], "hello")

    def test_get_recent_interactions_returns_saved_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.save_interaction("question", "answer")

                rows = db.get_recent_interactions()

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["user_text"], "question")
                self.assertEqual(rows[0]["assistant_reply"], "answer")

    def test_get_emotion_summary_empty_table_returns_count_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                summary = db.get_emotion_summary()

                self.assertEqual(summary["count"], 0)
                self.assertEqual(summary["emotions_count"], {})

    def test_memory_compatibility_class_can_be_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with Memory(self.make_db_path(temp_dir)) as db:
                event_id = db.insert_event("compat", payload={"works": True})

                row = db.get_event(event_id)

                self.assertIsNotNone(row)
                self.assertEqual(row["payload"], {"works": True})


if __name__ == "__main__":
    unittest.main()
