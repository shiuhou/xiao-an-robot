"""Unit tests for the voice-triggered screen usage report skill."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from agent.core.memory import XiaoAnMemoryStore
from agent.skills.screen_report import ScreenReportSkill


def _sample_usage_payload() -> dict:
    now_ms = int(time.time() * 1000)
    return {
        "source": "screen",
        "generated_at_ms": now_ms,
        "span_start_ms": now_ms - 3600_000,
        "span_end_ms": now_ms,
        "active_seconds": 5400,
        "away_seconds": 600,
        "total_keys": 3210,
        "total_clicks": 420,
        "total_scrolls": 88,
        "session_count": 14,
        "longest_session_seconds": 1800,
        "by_app": [
            {"app": "Code.exe", "seconds": 3600, "keys": 3000},
            {"app": "msedge.exe", "seconds": 1500, "keys": 210},
        ],
        "by_category": [
            {"category": "coding", "seconds": 3600},
            {"category": "browsing", "seconds": 1500},
        ],
        "by_domain": [
            {"domain": "github.com", "seconds": 900},
        ],
    }


class ScreenReportMatchTest(unittest.TestCase):
    def test_trigger_keywords_match(self) -> None:
        for text in (
            "汇总屏幕使用记录",
            "帮我汇总 屏幕使用时间",
            "生成一份屏幕使用报告",
            "屏幕报告",
        ):
            self.assertTrue(ScreenReportSkill.matches(text), text)

    def test_unrelated_text_does_not_match(self) -> None:
        for text in ("今天天气怎么样", "帮我加个待办", "我有点累", "", None):
            self.assertFalse(ScreenReportSkill.matches(text), repr(text))


class ScreenReportBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.store = XiaoAnMemoryStore(
            db_path=str(Path(self._temp.name) / "xiao_an.db"),
        )
        self.skill = ScreenReportSkill(memory_store=self.store)

    def tearDown(self) -> None:
        self.store.close()
        self._temp.cleanup()

    def test_report_with_usage_and_activities(self) -> None:
        self.store.insert_event(
            event_type="screen.usage_summary",
            source="screen",
            payload=_sample_usage_payload(),
        )
        self.store.insert_work_activity(
            source="screen",
            app_name="Code.exe",
            window_title="brain.py",
            activity_type="coding",
            project_hint="xiao-an-robot",
            note="给 brain 加屏幕报告路由",
            confidence=0.9,
            duration_seconds=1200,
        )

        report = self.skill.build_report()

        self.assertTrue(report["has_usage"])
        self.assertEqual(report["activity_count"], 1)
        self.assertIn("屏幕使用报告", report["title"])
        markdown = report["markdown"]
        self.assertIn("## 总览", markdown)
        self.assertIn("活跃时长：1小时30分", markdown)
        self.assertIn("最长连续专注：30分钟", markdown)
        self.assertIn("Code.exe：1小时00分", markdown)
        self.assertIn("github.com", markdown)
        self.assertIn("## 今天做了 1 件事", markdown)
        self.assertIn("给 brain 加屏幕报告路由", markdown)

    def test_report_degrades_without_usage_cache(self) -> None:
        report = self.skill.build_report()

        self.assertFalse(report["has_usage"])
        self.assertIn("还没有收到 PC 端的使用时长汇总", report["markdown"])

    def test_old_activities_are_excluded(self) -> None:
        self.store.insert_work_activity(
            source="screen",
            app_name="Code.exe",
            activity_type="coding",
            note="昨天的事",
            timestamp_ms=int(time.time() * 1000) - 2 * 24 * 3600 * 1000,
        )

        report = self.skill.build_report()

        self.assertEqual(report["activity_count"], 0)
        self.assertNotIn("昨天的事", report["markdown"])


if __name__ == "__main__":
    unittest.main()
