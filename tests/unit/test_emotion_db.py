"""Unit tests for base_station.monitor.emotion_db."""

from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path

from base_station.monitor.emotion_db import EmotionDB


class EmotionDBTest(unittest.TestCase):
    def make_db(self, temp_dir: str) -> EmotionDB:
        return EmotionDB(str(Path(temp_dir) / "test_emotions.db"))

    def make_old_schema_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE emotions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    source TEXT NOT NULL CHECK(source IN ('face', 'voice')),
                    emotion_tag TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fatigue_score REAL DEFAULT 0.0
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def emotion_columns(self, db: EmotionDB) -> set[str]:
        return {
            row["name"]
            for row in db.conn.execute("PRAGMA table_info(emotions)").fetchall()
        }

    def test_insert_emotion_returns_integer_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_db(temp_dir) as db:
                row_id = db.insert_emotion(
                    source="face",
                    emotion_tag="neutral",
                    confidence=0.8,
                    fatigue_score=0.3,
                )

                self.assertIsInstance(row_id, int)

    def test_old_schema_initialization_adds_polarity_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "old_schema.db"
            self.make_old_schema_db(db_path)

            with EmotionDB(str(db_path)) as db:
                self.assertIn("polarity", self.emotion_columns(db))

    def test_schema_migration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "old_schema.db"
            self.make_old_schema_db(db_path)

            with EmotionDB(str(db_path)) as db:
                self.assertIn("polarity", self.emotion_columns(db))
            with EmotionDB(str(db_path)) as db:
                self.assertIn("polarity", self.emotion_columns(db))

    def test_insert_emotion_succeeds_after_old_schema_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "old_schema.db"
            self.make_old_schema_db(db_path)

            with EmotionDB(str(db_path)) as db:
                row_id = db.insert_emotion(
                    source="face",
                    emotion_tag="neutral",
                    confidence=0.8,
                    fatigue_score=0.3,
                    polarity="正面",
                )
                row = db.conn.execute(
                    "SELECT polarity FROM emotions WHERE id = ?",
                    (row_id,),
                ).fetchone()

                self.assertEqual(row["polarity"], "正面")

    def test_query_recent_returns_only_records_inside_window(self) -> None:
        now_ms = 2_000_000
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_db(temp_dir) as db:
                db.insert_emotion("face", "neutral", 0.8, 0.3, timestamp=now_ms - 1000)
                db.insert_emotion("voice", "tired", 0.9, 0.7, timestamp=now_ms - 600000)

                rows = db.query_recent(seconds=300, now_ms=now_ms)

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["emotion_tag"], "neutral")

    def test_get_recent_summary_counts_recent_emotions(self) -> None:
        now_ms = 2_000_000
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_db(temp_dir) as db:
                db.insert_emotion("face", "tired", 0.7, 0.6, timestamp=now_ms - 1000)
                db.insert_emotion("voice", "anxious", 0.9, 0.4, timestamp=now_ms - 2000)
                db.insert_emotion("face", "tired", 0.8, 0.8, timestamp=now_ms - 3000)
                db.insert_emotion("voice", "neutral", 0.5, 0.2, timestamp=now_ms - 4000)

                summary = db.get_recent_summary(seconds=300, now_ms=now_ms)

                self.assertEqual(summary["count"], 4)
                self.assertAlmostEqual(summary["avg_fatigue_score"], 0.5)
                self.assertEqual(summary["max_confidence"], 0.9)
                self.assertEqual(summary["top_emotion"], "tired")
                self.assertEqual(summary["emotions_count"], {
                    "tired": 2,
                    "neutral": 1,
                    "anxious": 1,
                })

    def test_get_recent_summary_without_data_returns_empty_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_db(temp_dir) as db:
                summary = db.get_recent_summary(seconds=300, now_ms=2_000_000)

                self.assertEqual(summary["count"], 0)
                self.assertEqual(summary["avg_fatigue_score"], 0.0)
                self.assertIsNone(summary["top_emotion"])
                self.assertEqual(summary["emotions_count"], {})


if __name__ == "__main__":
    unittest.main()
