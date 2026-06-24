"""Unit tests for fake work activity samples."""

from __future__ import annotations

import unittest

from base_station.perception.work_activity import (
    FakeWorkActivitySource,
    WorkActivitySample,
)


class WorkActivityTest(unittest.TestCase):
    def test_fake_source_patterns(self) -> None:
        expected = {
            "coding": ("VS Code", "xiao-an-robot - memory.py", "coding", "xiao-an-robot", 0.85),
            "writing": ("Word", "项目设计方案书", "writing", "xiao-an-robot", 0.8),
            "browsing": ("Chrome", "OpenVINO documentation", "browsing", "xiao-an-robot", 0.75),
            "meeting": ("Tencent Meeting", "项目讨论会议", "meeting", "xiao-an-robot", 0.8),
            "idle": ("Desktop", "idle", "idle", None, 0.6),
            "unknown": ("Unknown", "unknown", "unknown", None, 0.0),
        }
        for pattern, values in expected.items():
            with self.subTest(pattern=pattern):
                sample = FakeWorkActivitySource(pattern).next_sample()

                self.assertEqual(sample.app_name, values[0])
                self.assertEqual(sample.window_title, values[1])
                self.assertEqual(sample.activity_type, values[2])
                self.assertEqual(sample.project_hint, values[3])
                self.assertEqual(sample.confidence, values[4])
                self.assertEqual(sample.source, "fake_work_activity")

    def test_work_activity_sample_to_dict(self) -> None:
        sample = WorkActivitySample(
            timestamp_ms=123,
            source="unit",
            app_name="Editor",
            window_title="file.py",
            activity_type="coding",
            project_hint="xiao-an-robot",
            confidence=0.9,
            duration_seconds=1.5,
        )

        self.assertEqual(sample.to_dict(), {
            "timestamp_ms": 123,
            "source": "unit",
            "app_name": "Editor",
            "window_title": "file.py",
            "activity_type": "coding",
            "project_hint": "xiao-an-robot",
            "confidence": 0.9,
            "duration_seconds": 1.5,
        })


if __name__ == "__main__":
    unittest.main()
