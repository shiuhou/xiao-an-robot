"""Unit tests for the live understanding loop (frames -> notes -> post).

Uses the offline `rule` understander (no network) and a fake `post_note`, so the
test exercises cursor/held-segment/ledger/unreachable logic without Qwen or a board.

Run from pc_screen_tracker/:
    python -m unittest tests.test_understand_loop
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tracker import understand_loop as ul_mod
from tracker.config import Config
from tracker.frames import FrameRecord
from tracker.store import Store
from tracker.understand_loop import UnderstandLoop


def _seed_three_windows(db_path: str, base_ms: int) -> None:
    """Three distinct windows in a row -> 3 segments (2 closed + 1 held tail)."""
    store = Store(db_path)
    idx = 0

    def add(app: str, title: str, content: list[str], start: int, n: int = 6, step: int = 3000) -> None:
        nonlocal idx
        for i in range(n):
            idx += 1
            store.insert_frame(FrameRecord(
                ts_ms=start + i * step, frame=idx, hwnd=abs(hash(app)) % 9999,
                app=app, title=title, kind="generic", capture_policy="full",
                content=list(content), mode="writing", keys=10,
            ))

    add("Code.exe", "brain.py", ["def handle_event(): screen report route"], base_ms)
    add("msedge.exe", "GitHub issue feishu", ["issue text about feishu doc create"], base_ms + 40_000)
    add("Code.exe", "loop.py", ["understand loop content"], base_ms + 80_000)
    store.close()


def _cfg(db_path: str) -> Config:
    cfg = Config()
    cfg.db_path = db_path
    cfg.understander_backend = "rule"      # offline, no network
    cfg.board_base_url = "http://fake-board"
    cfg.understand_enabled = True
    return cfg


class UnderstandLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self._tmp.name) / "usage.db")
        self.now = int(time.time() * 1000)
        self.base = self.now - 300_000       # 5 min ago, inside the default cursor window
        _seed_three_windows(self.db, self.base)
        self._orig_post = ul_mod.post_note

    def tearDown(self) -> None:
        ul_mod.post_note = self._orig_post
        self._tmp.cleanup()

    def _patch_post(self, result_fn):
        posted = []

        def fake_post(note, base_url, *, ledger=None, **kw):
            res = result_fn(note)
            if res.get("posted") and ledger is not None:
                ledger.mark(note)
            posted.append((note, res))
            return res

        ul_mod.post_note = fake_post
        return posted

    def _cursor(self) -> int:
        with open(str(Path(self._tmp.name) / "understand_cursor.json"), encoding="utf-8") as fh:
            return int(json.load(fh)["cursor_ms"])

    def test_posts_closed_segments_holds_last(self) -> None:
        posted = self._patch_post(lambda n: {"posted": True, "status": 200})
        loop = UnderstandLoop(_cfg(self.db))

        stats = loop.run_cycle(now_ms=self.now)

        self.assertEqual(stats["posted"], 2)          # 2 closed, last held back
        self.assertEqual(len(posted), 2)
        apps = [n.app_name for n, _ in posted]
        self.assertIn("Code.exe", apps)
        self.assertIn("msedge.exe", apps)
        # cursor sits just before the still-open tail (the 3rd window)
        self.assertEqual(self._cursor(), self.base + 80_000 - 1)

    def test_second_cycle_does_not_repost_held_tail(self) -> None:
        self._patch_post(lambda n: {"posted": True, "status": 200})
        loop = UnderstandLoop(_cfg(self.db))
        loop.run_cycle(now_ms=self.now)

        posted2 = self._patch_post(lambda n: {"posted": True, "status": 200})
        stats2 = loop.run_cycle(now_ms=self.now)

        self.assertEqual(stats2["posted"], 0)         # only the open tail remains
        self.assertEqual(len(posted2), 0)

    def test_unreachable_board_holds_cursor_for_retry(self) -> None:
        self._patch_post(lambda n: {"posted": False, "reason": "unreachable"})
        loop = UnderstandLoop(_cfg(self.db))

        stats = loop.run_cycle(now_ms=self.now)

        self.assertTrue(stats["unreachable"])
        self.assertEqual(stats["posted"], 0)
        # cursor did NOT advance to the tail; it rewinds to retry the first closed seg
        self.assertLess(self._cursor(), self.base + 80_000 - 1)

    def test_http_error_is_dropped_not_stuck(self) -> None:
        # (a) a board 4xx must not silently vanish AND must not poison the cursor
        self._patch_post(lambda n: {"posted": False, "reason": "http_error", "status": 400})
        loop = UnderstandLoop(_cfg(self.db))

        stats = loop.run_cycle(now_ms=self.now)

        self.assertEqual(stats["posted"], 0)
        self.assertEqual(stats["dropped"], 2)          # both closed segs 400'd
        self.assertFalse(stats["unreachable"])
        self.assertEqual(self._cursor(), self.base + 80_000 - 1)  # advanced, not stuck

    def test_already_delivered_segment_skips_ingest(self) -> None:
        # (b) a segment already in the ledger must be skipped BEFORE ingest,
        # so no second Qwen call is made for it.
        from tracker.segmenter import segment_frames
        store = Store(self.db)
        try:
            first_closed = segment_frames(store.query_frames(0))[0]
        finally:
            store.close()

        loop = UnderstandLoop(_cfg(self.db))
        loop.ledger.mark(SimpleNamespace(
            timestamp_ms=first_closed.start_ms, source="screen",
            app_name=first_closed.app, window_title=first_closed.title))

        ingested: list[str] = []
        real_ingest = loop.understander.ingest
        loop.understander.ingest = lambda seg: (ingested.append(seg.app) or real_ingest(seg))

        self._patch_post(lambda n: {"posted": True})
        stats = loop.run_cycle(now_ms=self.now)

        self.assertNotIn(first_closed.app, ingested)    # pre-delivered -> not re-ingested
        self.assertIn("msedge.exe", ingested)           # the other closed seg still runs
        self.assertGreaterEqual(stats["skipped"], 1)

    def test_disabled_without_board_url(self) -> None:
        cfg = _cfg(self.db)
        cfg.board_base_url = ""
        loop = UnderstandLoop(cfg)
        self.assertFalse(loop.enabled)
        loop.start()
        self.assertIsNone(loop._thread)

    def test_no_frames_advances_cursor(self) -> None:
        self._patch_post(lambda n: {"posted": True})
        loop = UnderstandLoop(_cfg(self.db))
        future = self.now + 10_000_000
        stats = loop.run_cycle(now_ms=future)
        self.assertEqual(stats["frames"], 0)
        self.assertEqual(self._cursor(), future)


if __name__ == "__main__":
    unittest.main()
