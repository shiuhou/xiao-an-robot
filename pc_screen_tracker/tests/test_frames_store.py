"""Unit test for the frames table (understanding-layer persistence).

Run from pc_screen_tracker/:
    python -m unittest tests.test_frames_store
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tracker.frames import FrameRecord
from tracker.store import Store


class FramesStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self._tmp.name) / "usage.db"))

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def test_frame_roundtrips_content_and_types(self) -> None:
        rec = FrameRecord(
            ts_ms=1_000, frame=1, hwnd=42, app="Code.exe", title="brain.py",
            kind="generic", capture_policy="full", url="",
            headline="brain.py",
            content=["def handle_event(): ...", "屏幕报告路由"],
            mode="writing", keys=12, clicks=1, scrolls=0, mouse_px=30.0,
            dwell_s=8.0, idle_s=0.0, uia_nodes=100, uia_docs=1,
            elapsed_ms=120, truncated=True,
        )
        self.store.insert_frame(rec)

        rows = self.store.query_frames(0)
        self.assertEqual(len(rows), 1)
        got = rows[0]
        self.assertEqual(got.app, "Code.exe")
        self.assertEqual(got.content, ["def handle_event(): ...", "屏幕报告路由"])
        self.assertIs(got.truncated, True)
        self.assertEqual(got.capture_policy, "full")

    def test_empty_content_survives(self) -> None:
        self.store.insert_frame(FrameRecord(ts_ms=2_000, frame=1, app="cmd.exe",
                                            capture_policy="none", content=[]))
        rows = self.store.query_frames(0)
        self.assertEqual(rows[0].content, [])
        self.assertIs(rows[0].truncated, False)

    def test_time_window_filter(self) -> None:
        for ts in (100, 200, 300):
            self.store.insert_frame(FrameRecord(ts_ms=ts, frame=ts, app="a.exe",
                                                content=["x"]))
        self.assertEqual([r.ts_ms for r in self.store.query_frames(150, 250)], [200])


if __name__ == "__main__":
    unittest.main()
