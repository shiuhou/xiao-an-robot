"""Unit test for the usage-summary payload + periodic pusher gating.

Run from pc_screen_tracker/:
    python -m unittest tests.test_summary_push
"""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tracker.report import Bucket, Report
from tracker.summary_push import SummaryPusher, summary_payload


def _sample_report() -> Report:
    rep = Report(span_start_ms=1720000000000, span_end_ms=1720003600000)
    rep.active_seconds = 5400.0
    rep.away_seconds = 600.0
    rep.total_keys = 3210
    rep.total_clicks = 420
    rep.total_scrolls = 88
    rep.by_app["Code.exe"] = Bucket(seconds=3600, keys=3000)
    rep.by_app["msedge.exe"] = Bucket(seconds=1500, keys=210)
    rep.by_category["coding"] = Bucket(seconds=3600)
    rep.by_domain["github.com"] = 900.0
    rep.timeline = [
        {"seconds": 3600, "app": "Code.exe"},
        {"seconds": 10, "app": "explorer.exe"},   # <30s: not a real session
        {"seconds": 1500, "app": "msedge.exe"},
    ]
    return rep


class TestSummaryPayload(unittest.TestCase):
    def test_payload_shape(self):
        payload = summary_payload(_sample_report())
        self.assertEqual(payload["source"], "screen")
        self.assertEqual(payload["active_seconds"], 5400)
        self.assertEqual(payload["away_seconds"], 600)
        self.assertEqual(payload["session_count"], 2)
        self.assertEqual(payload["longest_session_seconds"], 3600)
        self.assertEqual(payload["by_app"][0], {"app": "Code.exe", "seconds": 3600, "keys": 3000})
        self.assertEqual(payload["by_category"], [{"category": "coding", "seconds": 3600}])
        self.assertEqual(payload["by_domain"], [{"domain": "github.com", "seconds": 900}])
        self.assertIn("generated_at_ms", payload)

    def test_payload_carries_no_titles_or_urls(self):
        payload = summary_payload(_sample_report())
        for key in ("title", "window_title", "url", "content"):
            self.assertNotIn(key, payload)


class TestSummaryPusherGating(unittest.TestCase):
    def test_disabled_without_base_url(self):
        pusher = SummaryPusher(db_path=":memory:", base_url="", interval_s=1)
        self.assertFalse(pusher.enabled)
        self.assertIsNone(pusher.maybe_push())

    def test_interval_gate(self):
        pusher = SummaryPusher(db_path=":memory:", base_url="http://example", interval_s=9999)
        pusher._next_t = float("inf")  # pretend a push just happened
        self.assertIsNone(pusher.maybe_push())


if __name__ == "__main__":
    unittest.main()
