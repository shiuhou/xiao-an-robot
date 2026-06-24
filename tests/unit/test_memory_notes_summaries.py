"""Unit tests for notes and summaries in XiaoAnMemoryStore."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore


class MemoryNotesSummariesTest(unittest.TestCase):
    def _store(self, temp_dir: str) -> XiaoAnMemoryStore:
        db_path = Path(temp_dir) / "test_xiao_an.db"
        return XiaoAnMemoryStore(db_path=str(db_path))

    def test_insert_note_writes_memory_event_and_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                result = store.insert_note(
                    content="record current work",
                    tags=["work"],
                    project_hint="xiao-an-robot",
                    timestamp_ms=1000,
                )

                self.assertIsInstance(result["event_id"], int)
                self.assertIsInstance(result["note_id"], int)
                event = store.get_event(result["event_id"])
                self.assertIsNotNone(event)
                self.assertEqual(event["event_type"], "note.added")
                self.assertEqual(event["payload"]["content"], "record current work")
                notes = store.query_recent_notes()
                self.assertEqual(notes[0]["id"], result["note_id"])
                self.assertEqual(notes[0]["content"], "record current work")

    def test_query_recent_notes_parses_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_note("first", tags=["a", "b"], project_hint="p1")
                store.insert_note("second", tags=["b"], project_hint="p2")

                notes = store.query_recent_notes(project_hint="p1")

                self.assertEqual(len(notes), 1)
                self.assertEqual(notes[0]["content"], "first")
                self.assertEqual(notes[0]["tags"], ["a", "b"])

    def test_get_notes_summary_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                summary = store.get_notes_summary()

                self.assertEqual(summary["count"], 0)
                self.assertIsNone(summary["latest_content"])
                self.assertEqual(summary["tag_count"], {})

    def test_get_notes_summary_counts_tags_and_projects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_note("older", tags=["work"], project_hint="p1", timestamp_ms=1000)
                store.insert_note("newer", tags=["work", "daily"], project_hint="p1", timestamp_ms=2000)

                summary = store.get_notes_summary()

                self.assertEqual(summary["count"], 2)
                self.assertEqual(summary["latest_content"], "newer")
                self.assertEqual(summary["tag_count"]["work"], 2)
                self.assertEqual(summary["tag_count"]["daily"], 1)
                self.assertEqual(summary["project_hint_count"]["p1"], 2)

    def test_insert_summary_writes_memory_event_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                result = store.insert_summary(
                    summary_type="daily",
                    title="Daily Summary",
                    content="worked on memory",
                    date="2026-06-16",
                    metadata={"note_count": 2},
                    timestamp_ms=1000,
                )

                self.assertIsInstance(result["event_id"], int)
                self.assertIsInstance(result["summary_id"], int)
                event = store.get_event(result["event_id"])
                self.assertIsNotNone(event)
                self.assertEqual(event["event_type"], "summary.generated")
                summaries = store.query_recent_summaries()
                self.assertEqual(summaries[0]["id"], result["summary_id"])
                self.assertEqual(summaries[0]["metadata"], {"note_count": 2})

    def test_query_recent_summaries_filters_by_summary_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_summary("daily", "daily content", date="2026-06-16")
                store.insert_summary("weekly", "weekly content", date="2026-W25")

                summaries = store.query_recent_summaries(summary_type="daily")

                self.assertEqual(len(summaries), 1)
                self.assertEqual(summaries[0]["summary_type"], "daily")
                self.assertEqual(summaries[0]["content"], "daily content")

    def test_get_summary_overview_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                overview = store.get_summary_overview()

                self.assertEqual(overview["count"], 0)
                self.assertEqual(overview["summary_type_count"], {})
                self.assertIsNone(overview["latest_summary_type"])

    def test_get_summary_overview_counts_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_summary("daily", "older", title="Older", timestamp_ms=1000)
                store.insert_summary("daily", "newer", title="Newer", timestamp_ms=2000)
                store.insert_summary("weekly", "week", title="Week", timestamp_ms=1500)

                overview = store.get_summary_overview()

                self.assertEqual(overview["count"], 3)
                self.assertEqual(overview["summary_type_count"]["daily"], 2)
                self.assertEqual(overview["summary_type_count"]["weekly"], 1)
                self.assertEqual(overview["latest_summary_type"], "daily")
                self.assertEqual(overview["latest_title"], "Newer")


if __name__ == "__main__":
    unittest.main()
