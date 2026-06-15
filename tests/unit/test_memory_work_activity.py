"""Unit tests for work activity storage in XiaoAnMemoryStore."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore


class MemoryWorkActivityTest(unittest.TestCase):
    def make_db_path(self, temp_dir: str) -> str:
        return str(Path(temp_dir) / "memory_work_activity.db")

    def test_insert_work_activity_writes_event_and_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                result = db.insert_work_activity(
                    source="unit",
                    app_name="VS Code",
                    window_title="xiao-an-robot - memory.py",
                    activity_type="coding",
                    project_hint="xiao-an-robot",
                    confidence=0.85,
                    timestamp_ms=1000,
                )

                events = db.query_recent_events(event_type="work.activity")
                activities = db.query_recent_work_activities()

                self.assertIsInstance(result["event_id"], int)
                self.assertIsInstance(result["work_activity_id"], int)
                self.assertEqual(len(events), 1)
                self.assertEqual(len(activities), 1)
                self.assertEqual(activities[0]["event_id"], events[0]["id"])

    def test_memory_event_type_is_work_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_work_activity(activity_type="coding")

                event = db.query_recent_events()[0]

                self.assertEqual(event["event_type"], "work.activity")

    def test_query_recent_work_activities(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_work_activity(app_name="Word", activity_type="writing", timestamp_ms=1000)
                db.insert_work_activity(app_name="VS Code", activity_type="coding", timestamp_ms=2000)

                rows = db.query_recent_work_activities(limit=1)

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["app_name"], "VS Code")
                self.assertEqual(rows[0]["activity_type"], "coding")

    def test_get_recent_work_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_work_activity(
                    app_name="Word",
                    activity_type="writing",
                    project_hint="xiao-an-robot",
                    timestamp_ms=1000,
                )
                db.insert_work_activity(
                    app_name="VS Code",
                    activity_type="coding",
                    project_hint="xiao-an-robot",
                    timestamp_ms=2000,
                )
                db.insert_work_activity(
                    app_name="VS Code",
                    activity_type="coding",
                    project_hint="xiao-an-robot",
                    timestamp_ms=3000,
                )

                summary = db.get_recent_work_summary()

                self.assertEqual(summary["count"], 3)
                self.assertEqual(summary["latest_activity_type"], "coding")
                self.assertEqual(summary["latest_app_name"], "VS Code")
                self.assertEqual(summary["latest_project_hint"], "xiao-an-robot")
                self.assertEqual(summary["top_activity_type"], "coding")
                self.assertEqual(summary["top_app_name"], "VS Code")
                self.assertEqual(summary["activity_type_count"]["coding"], 2)
                self.assertEqual(summary["app_count"]["VS Code"], 2)
                self.assertEqual(summary["project_hint_count"]["xiao-an-robot"], 3)

    def test_query_filters_by_activity_type_and_project_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with XiaoAnMemoryStore(self.make_db_path(temp_dir)) as db:
                db.insert_work_activity(
                    activity_type="coding",
                    project_hint="xiao-an-robot",
                    timestamp_ms=1000,
                )
                db.insert_work_activity(
                    activity_type="writing",
                    project_hint="docs",
                    timestamp_ms=2000,
                )

                coding = db.query_recent_work_activities(activity_type="coding")
                docs = db.query_recent_work_activities(project_hint="docs")

                self.assertEqual(len(coding), 1)
                self.assertEqual(coding[0]["activity_type"], "coding")
                self.assertEqual(len(docs), 1)
                self.assertEqual(docs[0]["project_hint"], "docs")


if __name__ == "__main__":
    unittest.main()
