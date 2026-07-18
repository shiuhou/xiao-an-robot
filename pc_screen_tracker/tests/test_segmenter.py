"""Regression + L2-optimization tests for tracker.segmenter.

These lock in the behavior that was previously only verified ad-hoc ("7
synthetic tests") — no test file existed before (found during the L1-L6
optimization loop, ARCHITECTURE §14). Covers: identity split, idle break,
cap split, transient-glance absorb, same-identity coalesce, field-bleed
prevention, and the new content-drift boundary (L2 vision).
"""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tracker.frames import FrameRecord
from tracker.segmenter import segment_frames, IDLE_BREAK_S, MAX_SEG_S, MIN_SEG_S


def fr(ts_ms, app, title, *, content=None, kind="generic", url="",
       capture_policy="full", idle_s=0.0, mode="reading", frame=0) -> FrameRecord:
    return FrameRecord(
        ts_ms=ts_ms, frame=frame, app=app, title=title, kind=kind,
        capture_policy=capture_policy, url=url, content=content or [],
        mode=mode, idle_s=idle_s,
    )


class TestIdentitySplit(unittest.TestCase):
    def test_app_switch_splits_into_two_segments(self):
        frames = [
            fr(0, "chrome.exe", "A", content=["x" * 50]),
            fr(2000, "chrome.exe", "A", content=["x" * 50]),
            fr(4000, "Code.exe", "B.py", content=["y" * 50]),
            fr(6000, "Code.exe", "B.py", content=["y" * 50]),
        ]
        segs = segment_frames(frames, min_seg_s=0)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].app, "chrome.exe")
        self.assertEqual(segs[1].app, "Code.exe")


class TestIdleBreak(unittest.TestCase):
    def test_idle_gap_splits_same_identity_into_two_segments(self):
        frames = [
            fr(0, "chrome.exe", "A", content=["x" * 50]),
            fr(2000, "chrome.exe", "A", content=["x" * 50], idle_s=120, mode="idle"),
            fr(200_000, "chrome.exe", "A", content=["x" * 50]),
        ]
        segs = segment_frames(frames, idle_break_s=60, min_seg_s=0)
        self.assertEqual(len(segs), 2)


class TestCapSplit(unittest.TestCase):
    def test_over_cap_forces_a_new_segment(self):
        frames = [
            fr(i * 60_000, "chrome.exe", "A", content=["x" * 50])
            for i in range(12)  # 0..660s, cap at 600s
        ]
        segs = segment_frames(frames, max_seg_s=600, min_seg_s=0)
        self.assertGreaterEqual(len(segs), 2)


class TestTransientAbsorb(unittest.TestCase):
    def test_short_empty_glance_is_absorbed_not_a_segment(self):
        frames = [
            fr(0, "chrome.exe", "A", content=["x" * 50]),
            fr(2000, "chrome.exe", "A", content=["x" * 50]),
            fr(4000, "explorer.exe", "任务切换", content=[]),  # <8s, empty -> transient
            fr(6000, "chrome.exe", "A", content=["x" * 50]),
            fr(8000, "chrome.exe", "A", content=["x" * 50]),
        ]
        segs = segment_frames(frames, min_seg_s=8)
        apps = [s.app for s in segs]
        self.assertNotIn("explorer.exe", apps)

    def test_short_segment_with_real_content_is_kept(self):
        # a quick zhihu search is short but has content -> must NOT be folded away
        frames = [
            fr(0, "chrome.exe", "A", content=["x" * 50]),
            fr(2000, "chrome.exe", "A", content=["x" * 50]),
            fr(4000, "chrome.exe", "港科广 - 知乎", content=["搜索结果内容" * 5], url="zhihu.com"),
            fr(6000, "chrome.exe", "A", content=["x" * 50]),
            fr(8000, "chrome.exe", "A", content=["x" * 50]),
        ]
        segs = segment_frames(frames, min_seg_s=8)
        titles = [s.title for s in segs]
        self.assertTrue(any("知乎" in t for t in titles))


class TestFieldBleedPrevention(unittest.TestCase):
    def test_absorbed_glance_does_not_overwrite_neighbour_title(self):
        frames = [
            fr(0, "chrome.exe", "chrome-title", content=["x" * 50]),
            fr(2000, "WindowsTerminal.exe", "terminal-title", content=[]),  # transient, empty
            fr(4000, "chrome.exe", "chrome-title", content=["x" * 50]),
        ]
        segs = segment_frames(frames, min_seg_s=8)
        for s in segs:
            self.assertNotIn("terminal-title", s.title)


class TestCoalesce(unittest.TestCase):
    def test_adjacent_same_identity_segments_merge(self):
        frames = [
            fr(0, "chrome.exe", "A", content=["short"]),
            fr(9000, "chrome.exe", "A", content=["a much longer richer body of text here"]),
        ]
        segs = segment_frames(frames, min_seg_s=0)
        self.assertEqual(len(segs), 1)
        self.assertIn("richer", segs[0].content[0])


class TestContentDrift(unittest.TestCase):
    """L2 optimization (ARCHITECTURE §14): same identity, but content moves to
    a genuinely different topic (SPA / infinite-scroll page whose URL/title
    never changes) must still get a boundary."""

    def test_unrelated_content_under_same_identity_splits(self):
        topic_a = ["讨论港科广招生政策与港科广宿舍安排的详细说明文字段落"] * 3
        topic_b = ["关于机器学习模型训练调参与神经网络架构搜索的技术讨论段落"] * 3
        frames = [
            fr(0, "chrome.exe", "SPA", content=topic_a, url="app.example.com"),
            fr(30_000, "chrome.exe", "SPA", content=topic_a, url="app.example.com"),
            fr(60_000, "chrome.exe", "SPA", content=topic_b, url="app.example.com"),
            fr(90_000, "chrome.exe", "SPA", content=topic_b, url="app.example.com"),
        ]
        segs = segment_frames(frames, min_seg_s=0)
        self.assertEqual(len(segs), 2, f"expected a drift split, got {len(segs)} segment(s)")

    def test_similar_content_under_same_identity_does_not_split(self):
        # scrolled variations of the SAME topic must NOT be treated as drift
        base = "港科广招生政策 宿舍安排 校园环境 交通指南 学费详情"
        frames = [
            fr(0, "chrome.exe", "SPA", content=[base], url="app.example.com"),
            fr(30_000, "chrome.exe", "SPA", content=[base + " 补充说明"], url="app.example.com"),
            fr(60_000, "chrome.exe", "SPA", content=[base + " 更多细节"], url="app.example.com"),
        ]
        segs = segment_frames(frames, min_seg_s=0)
        self.assertEqual(len(segs), 1)

    def test_short_content_does_not_trigger_drift(self):
        # below DRIFT_MIN_CHARS -> too little signal to judge, must not split
        frames = [
            fr(0, "chrome.exe", "SPA", content=["ok"], url="app.example.com"),
            fr(30_000, "chrome.exe", "SPA", content=["no"], url="app.example.com"),
        ]
        segs = segment_frames(frames, min_seg_s=0)
        self.assertEqual(len(segs), 1)

    def test_single_divergent_frame_does_not_confirm_drift(self):
        # ONE off-topic frame among otherwise on-topic samples must NOT split —
        # this is the real false positive found on real data (one frame only
        # captured shallow/noisy extraction, e.g. tab-bar chrome text, before
        # the next frame read the real body again). Drift needs TWO confirming
        # divergent frames to fire (see _split_one_run).
        topic_a = ["讨论港科广招生政策与港科广宿舍安排的详细说明文字段落"] * 3
        topic_b = ["关于机器学习模型训练调参与神经网络架构搜索的技术讨论段落"] * 3
        frames = [
            fr(0, "chrome.exe", "SPA", content=topic_a, url="app.example.com"),
            fr(30_000, "chrome.exe", "SPA", content=topic_a, url="app.example.com"),
            fr(60_000, "chrome.exe", "SPA", content=topic_b, url="app.example.com"),  # single blip
            fr(90_000, "chrome.exe", "SPA", content=topic_a, url="app.example.com"),  # back on-topic
        ]
        segs = segment_frames(frames, min_seg_s=0)
        self.assertEqual(len(segs), 1)

    def test_shallow_first_frame_does_not_anchor_a_false_split(self):
        # regression test for a REAL false positive found on real data: VSCode's
        # first extraction only caught tab-bar/breadcrumb chrome + an unrelated
        # notification toast (short, low-signal); the next 4 frames all
        # consistently captured the real code body. This must stay ONE
        # segment (same file being read, not a topic change) — the shallow
        # frame must be skipped when choosing the anchor.
        shallow_junk = ["report.py - screen-tracker - Visual Studio Code"]  # ~48 chars
        real_code = ['"""Derive usage statistics from raw samples and render '
                     'console reports.""" from __future__ import annotations '
                     'import statistics helper module code body defines a '
                     'Bucket dataclass and formatting helpers for durations '
                     'used across the report renderer implementation here']  # ~280 chars
        frames = [
            fr(0, "Code.exe", "report.py", content=shallow_junk, kind="generic"),
            fr(2000, "Code.exe", "report.py", content=real_code, kind="generic"),
            fr(4000, "Code.exe", "report.py", content=real_code, kind="generic"),
            fr(6000, "Code.exe", "report.py", content=real_code, kind="generic"),
            fr(8000, "Code.exe", "report.py", content=real_code, kind="generic"),
        ]
        segs = segment_frames(frames, min_seg_s=0)
        self.assertEqual(len(segs), 1)

    def test_drift_boundary_is_hard_and_survives_coalesce(self):
        # after a CONFIRMED drift split (2 divergent frames), a further frame
        # back on topic_a (same identity) must not silently re-merge across
        # the drift boundary
        topic_a = ["讨论港科广招生政策与港科广宿舍安排的详细说明文字段落"] * 3
        topic_b = ["关于机器学习模型训练调参与神经网络架构搜索的技术讨论段落"] * 3
        frames = [
            fr(0, "chrome.exe", "SPA", content=topic_a, url="app.example.com"),
            fr(30_000, "chrome.exe", "SPA", content=topic_a, url="app.example.com"),
            fr(60_000, "chrome.exe", "SPA", content=topic_b, url="app.example.com"),
            fr(90_000, "chrome.exe", "SPA", content=topic_b, url="app.example.com"),  # confirms
        ]
        segs = segment_frames(frames, min_seg_s=0)
        self.assertEqual(len(segs), 2)
        self.assertIn("招生", segs[0].content[0])
        self.assertIn("机器学习", segs[1].content[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
