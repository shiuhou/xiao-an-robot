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

    def test_insert_and_read_back_new_engine_fields(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_db(temp_dir) as db:
                row_id = db.insert_emotion(
                    source="face",
                    emotion_tag="Sad",
                    confidence=0.7,
                    fatigue_score=0.72,
                    polarity="负面",
                    timestamp=1000,
                    fatigue_level="high",
                    observation_quality=0.81,
                    evidence_codes=["LONG_CLOSURE", "PERCLOS_HIGH"],
                    algorithm_version="rule_v0",
                    presence_state="present",
                    valence="negative",
                    au_json={"AU45": 0.9},
                )
                row = db.conn.execute(
                    "SELECT fatigue_level, observation_quality, evidence_codes, "
                    "algorithm_version, presence_state, valence, au_json "
                    "FROM emotions WHERE id = ?",
                    (row_id,),
                ).fetchone()

                self.assertEqual(row["fatigue_level"], "high")
                self.assertAlmostEqual(row["observation_quality"], 0.81)
                self.assertEqual(json.loads(row["evidence_codes"]), ["LONG_CLOSURE", "PERCLOS_HIGH"])
                self.assertEqual(row["algorithm_version"], "rule_v0")
                self.assertEqual(row["presence_state"], "present")
                self.assertEqual(row["valence"], "negative")
                self.assertEqual(json.loads(row["au_json"]), {"AU45": 0.9})

    def test_old_schema_migration_adds_new_engine_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "old_schema.db"
            self.make_old_schema_db(db_path)

            with EmotionDB(str(db_path)) as db:
                cols = self.emotion_columns(db)
                for c in (
                    "fatigue_level", "observation_quality", "evidence_codes",
                    "algorithm_version", "presence_state", "valence", "au_json",
                ):
                    self.assertIn(c, cols)

    def test_summary_reports_most_severe_fatigue_level(self) -> None:
        now_ms = 2_000_000
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_db(temp_dir) as db:
                db.insert_emotion("face", "Neutral", 0.5, 0.1, timestamp=now_ms - 1000, fatigue_level="low")
                db.insert_emotion("face", "Sad", 0.8, 0.7, timestamp=now_ms - 2000, fatigue_level="high")
                db.insert_emotion("face", "Neutral", 0.6, 0.3, timestamp=now_ms - 3000, fatigue_level="medium")

                summary = db.get_recent_summary(seconds=300, now_ms=now_ms)

                self.assertEqual(summary["fatigue_level_top"], "high")
                self.assertEqual(summary["fatigue_levels_count"], {"low": 1, "high": 1, "medium": 1})

    def test_summary_excludes_none_fatigue_score_from_average(self) -> None:
        now_ms = 2_000_000
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.make_db(temp_dir) as db:
                db.insert_emotion("face", "Neutral", 0.5, 0.4, timestamp=now_ms - 1000, fatigue_level="low")
                db.insert_emotion("face", "Neutral", 0.5, None, timestamp=now_ms - 2000, fatigue_level="insufficient_evidence")

                summary = db.get_recent_summary(seconds=300, now_ms=now_ms)

                self.assertAlmostEqual(summary["avg_fatigue_score"], 0.4)


if __name__ == "__main__":
    unittest.main()
