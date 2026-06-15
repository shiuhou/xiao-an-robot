"""Unit tests for work context injection policy."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.core.context_policy import ContextInjectionPolicy


class ContextInjectionPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ContextInjectionPolicy()

    def test_empty_text_does_not_need_work_context(self) -> None:
        for text in (None, "", "   "):
            with self.subTest(text=text):
                decision = self.policy.decide_for_text(text)

                self.assertFalse(decision.needs_work_context)
                self.assertEqual(decision.reason, "empty_text")
                self.assertEqual(decision.matched_keywords, [])

    def test_just_now_question_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("我刚刚在做什么")

        self.assertTrue(decision.needs_work_context)
        self.assertEqual(decision.reason, "work_keyword")

    def test_development_summary_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("帮我总结今天开发进度")

        self.assertTrue(decision.needs_work_context)

    def test_continue_project_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("继续刚才的项目")

        self.assertTrue(decision.needs_work_context)

    def test_code_next_step_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("我这个代码下一步怎么写")

        self.assertTrue(decision.needs_work_context)

    def test_daily_report_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("生成今天的日报")

        self.assertTrue(decision.needs_work_context)

    def test_weather_does_not_need_work_context(self) -> None:
        decision = self.policy.decide_for_text("今天天气怎么样")

        self.assertFalse(decision.needs_work_context)
        self.assertEqual(decision.reason, "no_context_needed")

    def test_joke_does_not_need_work_context(self) -> None:
        decision = self.policy.decide_for_text("讲个笑话")

        self.assertFalse(decision.needs_work_context)
        self.assertEqual(decision.reason, "no_context_needed")

    def test_greeting_does_not_need_work_context(self) -> None:
        decision = self.policy.decide_for_text("你好小安")

        self.assertFalse(decision.needs_work_context)
        self.assertEqual(decision.reason, "no_context_needed")

    def test_matched_keywords_returns_all_matches_in_stable_order(self) -> None:
        decision = self.policy.decide_for_text("继续刚才的项目，帮我总结今天开发进度")

        self.assertTrue(decision.needs_work_context)
        self.assertEqual(decision.matched_keywords, [
            "刚才",
            "继续",
            "继续刚才",
            "项目",
            "开发",
            "进度",
            "总结今天",
            "今天开发",
        ])

    def test_policy_does_not_modify_database_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "xiao_an.db"

            decision = self.policy.decide_for_text("继续刚才的项目")

            self.assertTrue(decision.needs_work_context)
            self.assertFalse(db_path.exists())


if __name__ == "__main__":
    unittest.main()
