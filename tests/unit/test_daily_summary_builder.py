"""Unit tests for DailySummaryBuilder."""

from __future__ import annotations

import unittest
from datetime import date as date_type

from agent.core.daily_summary_builder import DailySummaryBuilder


class FakeSummaryMemory:
    def __init__(self, raise_method: str | None = None) -> None:
        self.raise_method = raise_method
        self.work_summary = {}
        self.work_activities = []
        self.notes_summary = {}
        self.notes = []
        self.tasks_summary = {}
        self.tasks = []
        self.reminders_summary = {}
        self.reminders = []
        self.tool_summary = {}
        self.tool_runs = []
        self.emotion_summary = {}

    def _maybe_raise(self, method_name: str) -> None:
        if self.raise_method == method_name:
            raise RuntimeError(f"{method_name} failed")

    def get_recent_work_summary(self, limit: int = 20) -> dict:
        self._maybe_raise("get_recent_work_summary")
        return self.work_summary

    def query_recent_work_activities(self, limit: int = 20) -> list:
        self._maybe_raise("query_recent_work_activities")
        return self.work_activities

    def get_notes_summary(self, limit: int = 20) -> dict:
        self._maybe_raise("get_notes_summary")
        return self.notes_summary

    def query_recent_notes(self, limit: int = 20, project_hint=None) -> list:
        self._maybe_raise("query_recent_notes")
        return self.notes

    def get_tasks_summary(self, limit: int = 20) -> dict:
        self._maybe_raise("get_tasks_summary")
        return self.tasks_summary

    def query_tasks(self, limit: int = 20, include_done: bool = False, project_hint=None) -> list:
        self._maybe_raise("query_tasks")
        return self.tasks

    def get_reminders_summary(self, limit: int = 20) -> dict:
        self._maybe_raise("get_reminders_summary")
        return self.reminders_summary

    def query_reminders(self, limit: int = 20, include_fired: bool = False) -> list:
        self._maybe_raise("query_reminders")
        return self.reminders

    def get_tool_run_summary(self, limit: int = 20) -> dict:
        self._maybe_raise("get_tool_run_summary")
        return self.tool_summary

    def query_recent_tool_runs(self, limit: int = 20) -> list:
        self._maybe_raise("query_recent_tool_runs")
        return self.tool_runs

    def get_emotion_summary(self, hours: int = 24) -> dict:
        self._maybe_raise("get_emotion_summary")
        return self.emotion_summary


class DailySummaryBuilderTest(unittest.TestCase):
    def test_empty_memory_generates_non_empty_content(self) -> None:
        summary = DailySummaryBuilder(FakeSummaryMemory()).build(date="2026-06-16")

        self.assertTrue(summary["content"])
        self.assertIn("暂无", summary["content"])

    def test_work_summary_appears_in_content(self) -> None:
        memory = FakeSummaryMemory()
        memory.work_summary = {
            "count": 3,
            "top_activity_type": "coding",
            "top_app_name": "VS Code",
            "latest_project_hint": "xiao-an-robot",
        }

        summary = DailySummaryBuilder(memory).build(date="2026-06-16")

        self.assertIn("coding", summary["content"])
        self.assertIn("VS Code", summary["content"])
        self.assertIn("xiao-an-robot", summary["content"])

    def test_notes_appear_in_content(self) -> None:
        memory = FakeSummaryMemory()
        memory.notes = [{"content": "明天下午交报告"}]

        summary = DailySummaryBuilder(memory).build(date="2026-06-16")

        self.assertIn("明天下午交报告", summary["content"])

    def test_tasks_appear_in_content(self) -> None:
        memory = FakeSummaryMemory()
        memory.tasks = [
            {"title": "明天下午交报告", "status": "pending"},
            {"title": "完成 Step 22", "status": "done"},
        ]

        summary = DailySummaryBuilder(memory).build(date="2026-06-16")

        self.assertIn("待办：明天下午交报告", summary["content"])
        self.assertIn("已完成：完成 Step 22", summary["content"])

    def test_reminders_appear_in_content(self) -> None:
        memory = FakeSummaryMemory()
        memory.reminders = [
            {"message": "该休息一下了", "status": "pending"},
            {"message": "喝水", "status": "fired"},
        ]

        summary = DailySummaryBuilder(memory).build(date="2026-06-16")

        self.assertIn("待触发：该休息一下了", summary["content"])
        self.assertIn("已触发：喝水", summary["content"])

    def test_tool_runs_appear_in_content(self) -> None:
        memory = FakeSummaryMemory()
        memory.tool_summary = {"count": 4, "tool_count": {"note.add": 2, "summary.daily": 1}}

        summary = DailySummaryBuilder(memory).build(date="2026-06-16")

        self.assertIn("note.add: 2", summary["content"])
        self.assertIn("summary.daily: 1", summary["content"])

    def test_memory_method_error_is_recorded(self) -> None:
        memory = FakeSummaryMemory(raise_method="query_recent_notes")

        summary = DailySummaryBuilder(memory).build(date="2026-06-16")

        self.assertTrue(summary["content"])
        self.assertEqual(summary["metadata"]["errors"][0]["scope"], "query_recent_notes")

    def test_returns_daily_summary_type(self) -> None:
        summary = DailySummaryBuilder(FakeSummaryMemory()).build(date="2026-06-16")

        self.assertEqual(summary["summary_type"], "daily")

    def test_returns_required_fields(self) -> None:
        summary = DailySummaryBuilder(FakeSummaryMemory()).build(date="2026-06-16")

        self.assertEqual(summary["title"], "小安日报 - 2026-06-16")
        self.assertEqual(summary["date"], "2026-06-16")
        self.assertIsInstance(summary["content"], str)
        self.assertIsInstance(summary["metadata"], dict)
        self.assertIn("今日概览", summary["metadata"]["sections"])

    def test_none_date_uses_today_iso_date(self) -> None:
        summary = DailySummaryBuilder(FakeSummaryMemory()).build(date=None)

        self.assertEqual(summary["date"], date_type.today().isoformat())
        self.assertIsNotNone(summary["date"])

    def test_today_date_is_normalized(self) -> None:
        summary = DailySummaryBuilder(FakeSummaryMemory()).build(date="today")

        self.assertEqual(summary["date"], date_type.today().isoformat())
        self.assertNotEqual(summary["date"], "today")
        self.assertNotIn("today", summary["title"])

    def test_chinese_today_date_is_normalized(self) -> None:
        summary = DailySummaryBuilder(FakeSummaryMemory()).build(date="今天")

        self.assertEqual(summary["date"], date_type.today().isoformat())

    def test_iso_date_is_preserved(self) -> None:
        summary = DailySummaryBuilder(FakeSummaryMemory()).build(date="2026-06-16")

        self.assertEqual(summary["date"], "2026-06-16")


if __name__ == "__main__":
    unittest.main()
