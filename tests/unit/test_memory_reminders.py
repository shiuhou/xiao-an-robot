"""Unit tests for reminder memory APIs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore


class MemoryRemindersTest(unittest.TestCase):
    def _store(self, temp_dir: str) -> XiaoAnMemoryStore:
        return XiaoAnMemoryStore(db_path=str(Path(temp_dir) / "reminders.db"))

    def test_insert_reminder_writes_event_and_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                result = store.insert_reminder("stand up", delay_seconds=60)

                self.assertIsInstance(result["event_id"], int)
                self.assertIsInstance(result["reminder_id"], int)
                event = store.get_event(result["event_id"])
                self.assertEqual(event["event_type"], "reminder.added")
                self.assertEqual(event["payload"]["message"], "stand up")
                reminders = store.query_reminders()
                self.assertEqual(reminders[0]["message"], "stand up")
                self.assertEqual(reminders[0]["status"], "pending")

    def test_query_reminders_defaults_to_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                first = store.insert_reminder("pending", due_at_ms=1000)
                second = store.insert_reminder("fired", due_at_ms=1000)
                store.mark_reminder_fired(second["reminder_id"], fired_at_ms=2000)

                reminders = store.query_reminders()

                self.assertEqual(len(reminders), 1)
                self.assertEqual(reminders[0]["id"], first["reminder_id"])

    def test_query_due_reminders_only_returns_due_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                due = store.insert_reminder("due", due_at_ms=1000)
                store.insert_reminder("later", due_at_ms=3000)
                fired = store.insert_reminder("already fired", due_at_ms=500)
                store.mark_reminder_fired(fired["reminder_id"], fired_at_ms=800)

                reminders = store.query_due_reminders(now_ms=2000)

                self.assertEqual(len(reminders), 1)
                self.assertEqual(reminders[0]["id"], due["reminder_id"])

    def test_mark_reminder_fired_updates_status_and_writes_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                result = store.insert_reminder("wake me", due_at_ms=1000)

                fired = store.mark_reminder_fired(result["reminder_id"], fired_at_ms=2000)

                self.assertTrue(fired["ok"])
                reminders = store.query_reminders(status="fired", include_fired=True)
                self.assertEqual(reminders[0]["fired_at_ms"], 2000)
                event = store.get_event(fired["event_id"])
                self.assertEqual(event["event_type"], "reminder.fired")

    def test_cancel_reminder_by_id_updates_status_and_writes_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                result = store.insert_reminder("cancel me", due_at_ms=1000)

                cancelled = store.cancel_reminder(reminder_id=result["reminder_id"])

                self.assertTrue(cancelled["ok"])
                reminders = store.query_reminders(status="cancelled", include_fired=True)
                self.assertEqual(reminders[0]["message"], "cancel me")
                event = store.get_event(cancelled["event_id"])
                self.assertEqual(event["event_type"], "reminder.cancelled")

    def test_cancel_reminder_by_message_contains(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_reminder("drink water", due_at_ms=1000)

                cancelled = store.cancel_reminder(message_contains="water")

                self.assertTrue(cancelled["ok"])
                self.assertEqual(cancelled["message"], "drink water")

    def test_cancel_reminder_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                result = store.cancel_reminder(message_contains="missing")

                self.assertFalse(result["ok"])
                self.assertEqual(result["reason"], "not_found")

    def test_get_reminders_summary_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                summary = store.get_reminders_summary()

                self.assertEqual(summary["count"], 0)
                self.assertEqual(summary["pending_count"], 0)
                self.assertEqual(summary["status_count"], {})

    def test_get_reminders_summary_counts_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                pending = store.insert_reminder("pending", due_at_ms=1000)
                fired = store.insert_reminder("fired", due_at_ms=1000)
                cancelled = store.insert_reminder("cancelled", due_at_ms=1000)
                store.mark_reminder_fired(fired["reminder_id"], fired_at_ms=2000)
                store.cancel_reminder(reminder_id=cancelled["reminder_id"])

                summary = store.get_reminders_summary()

                self.assertEqual(summary["count"], 3)
                self.assertEqual(summary["pending_count"], 1)
                self.assertEqual(summary["fired_count"], 1)
                self.assertEqual(summary["cancelled_count"], 1)
                self.assertEqual(summary["status_count"]["pending"], 1)
                self.assertEqual(summary["latest_message"], "cancelled")


if __name__ == "__main__":
    unittest.main()
