"""Unit tests for fake work activity runtime."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore
from base_station.monitor.work_activity_runtime import main, parse_args, run_samples


class WorkActivityRuntimeTest(unittest.TestCase):
    def make_db_path(self, temp_dir: str) -> str:
        return str(Path(temp_dir) / "runtime_work_activity.db")

    def test_run_samples_writes_to_temp_db(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self.make_db_path(temp_dir)

            outputs = run_samples(
                pattern="coding",
                count=2,
                interval=0,
                db_path=db_path,
                fresh_db=False,
            )

            with XiaoAnMemoryStore(db_path) as db:
                rows = db.query_recent_work_activities()
                events = db.query_recent_events(event_type="work.activity")

            self.assertEqual(len(outputs), 2)
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(events), 2)
            self.assertEqual(outputs[-1]["summary"]["count"], 2)

    def test_main_accepts_args_and_returns_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self.make_db_path(temp_dir)
            args = parse_args([
                "--pattern",
                "writing",
                "--count",
                "1",
                "--interval",
                "0",
                "--db-path",
                db_path,
            ])

            outputs = main(args)

            self.assertEqual(len(outputs), 1)
            self.assertEqual(outputs[0]["sample"]["activity_type"], "writing")
            self.assertEqual(outputs[0]["summary"]["latest_activity_type"], "writing")

    def test_fresh_db_does_not_pollute_requested_default_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self.make_db_path(temp_dir)

            outputs = run_samples(
                pattern="idle",
                count=1,
                interval=0,
                db_path=db_path,
                fresh_db=True,
            )

            self.assertEqual(len(outputs), 1)
            self.assertFalse(Path(db_path).exists())


if __name__ == "__main__":
    unittest.main()
