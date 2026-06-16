"""Unit tests for ReminderScheduler."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore
from agent.core.reminder_scheduler import ReminderScheduler


class FakeRobot:
    def __init__(self, raise_error: bool = False) -> None:
        self.raise_error = raise_error
        self.say_calls = []

    async def say(self, text: str) -> dict:
        if self.raise_error:
            raise RuntimeError("robot unavailable")
        self.say_calls.append(text)
        return {"ok": True, "text": text}


class ReminderSchedulerTest(unittest.IsolatedAsyncioTestCase):
    def _store(self, temp_dir: str) -> XiaoAnMemoryStore:
        return XiaoAnMemoryStore(db_path=str(Path(temp_dir) / "reminders.db"))

    async def test_tick_without_due_reminders_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                robot = FakeRobot()
                scheduler = ReminderScheduler(store, robot_motion=robot)

                result = await scheduler.tick()

                self.assertEqual(result["fired_count"], 0)
                self.assertEqual(robot.say_calls, [])

    async def test_tick_calls_robot_for_due_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                store.insert_reminder("wake up", due_at_ms=1)
                robot = FakeRobot()
                scheduler = ReminderScheduler(store, robot_motion=robot)

                result = await scheduler.tick()

                self.assertEqual(result["fired_count"], 1)
                self.assertEqual(robot.say_calls, ["wake up"])

    async def test_tick_marks_successful_reminder_fired(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                created = store.insert_reminder("wake up", due_at_ms=1)
                scheduler = ReminderScheduler(store, robot_motion=FakeRobot())

                await scheduler.tick()

                reminders = store.query_reminders(status="fired", include_fired=True)
                self.assertEqual(reminders[0]["id"], created["reminder_id"])

    async def test_robot_failure_does_not_mark_fired(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                created = store.insert_reminder("wake up", due_at_ms=1)
                scheduler = ReminderScheduler(store, robot_motion=FakeRobot(raise_error=True))

                result = await scheduler.tick()

                self.assertEqual(result["fired_count"], 0)
                self.assertEqual(result["errors"][0]["reminder_id"], created["reminder_id"])
                reminders = store.query_reminders()
                self.assertEqual(reminders[0]["status"], "pending")

    async def test_tick_does_not_trigger_future_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                future_ms = int(time.time() * 1000) + 60_000
                store.insert_reminder("later", due_at_ms=future_ms)
                robot = FakeRobot()
                scheduler = ReminderScheduler(store, robot_motion=robot)

                result = await scheduler.tick()

                self.assertEqual(result["fired_count"], 0)
                self.assertEqual(robot.say_calls, [])

    async def test_tick_respects_max_due_per_tick(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self._store(temp_dir) as store:
                for index in range(3):
                    store.insert_reminder(f"reminder {index}", due_at_ms=1)
                robot = FakeRobot()
                scheduler = ReminderScheduler(store, robot_motion=robot, max_due_per_tick=2)

                result = await scheduler.tick()

                self.assertEqual(result["fired_count"], 2)
                self.assertEqual(len(robot.say_calls), 2)
                self.assertEqual(len(store.query_reminders()), 1)


if __name__ == "__main__":
    unittest.main()
