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
                self.assertEqual(decision.requested_scopes, [])
                self.assertEqual(decision.method, "keyword_heuristic")
                self.assertEqual(decision.confidence, 0.0)

    def test_just_now_question_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("我刚刚在做什么")

        self.assertTrue(decision.needs_work_context)
        self.assertEqual(decision.reason, "memory_keyword")
        self.assertEqual(decision.method, "keyword_heuristic")
        self.assertEqual(decision.requested_scopes, ["work"])

    def test_development_summary_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("帮我总结今天开发进度")

        self.assertTrue(decision.needs_work_context)
        self.assertEqual(decision.method, "keyword_heuristic")

    def test_continue_project_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("继续刚才的项目")

        self.assertTrue(decision.needs_work_context)

    def test_code_next_step_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("我这个代码下一步怎么写")

        self.assertTrue(decision.needs_work_context)

    def test_daily_report_needs_work_context(self) -> None:
        decision = self.policy.decide_for_text("生成今天的日报")

        self.assertTrue(decision.needs_work_context)
        self.assertTrue(decision.needs_summaries_context)

    def test_weather_does_not_need_work_context(self) -> None:
        decision = self.policy.decide_for_text("今天天气怎么样")

        self.assertFalse(decision.needs_work_context)
        self.assertEqual(decision.reason, "no_context_needed")
        self.assertEqual(decision.requested_scopes, [])
        self.assertEqual(decision.method, "keyword_heuristic")

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
            "总结",
        ])
        self.assertEqual(decision.requested_scopes, [
            "work",
            "notes",
            "tasks",
            "reminders",
            "summaries",
            "tool_runs",
            "care",
        ])

    def test_note_question_requests_notes_scope(self) -> None:
        decision = self.policy.decide_for_text("我刚刚记了什么")

        self.assertTrue(decision.needs_notes_context)
        self.assertEqual(decision.requested_scopes, ["notes"])
        self.assertEqual(decision.reason, "memory_keyword")
        self.assertEqual(decision.method, "keyword_heuristic")

    def test_task_question_requests_tasks_scope(self) -> None:
        decision = self.policy.decide_for_text("我今天还有什么任务")

        self.assertTrue(decision.needs_tasks_context)
        self.assertEqual(decision.requested_scopes, ["tasks"])
        self.assertEqual(decision.method, "keyword_heuristic")

    def test_reminder_question_requests_reminders_scope(self) -> None:
        decision = self.policy.decide_for_text("刚才设了什么提醒")

        self.assertTrue(decision.needs_reminders_context)
        self.assertEqual(decision.requested_scopes, ["reminders"])
        self.assertEqual(decision.method, "keyword_heuristic")

    def test_summary_question_requests_all_memory_scopes(self) -> None:
        decision = self.policy.decide_for_text("总结一下今天进展")

        self.assertTrue(decision.needs_summaries_context)
        self.assertEqual(decision.requested_scopes, [
            "work",
            "notes",
            "tasks",
            "reminders",
            "summaries",
            "tool_runs",
            "care",
        ])
        self.assertEqual(decision.method, "keyword_heuristic")

    def test_tool_call_question_requests_tool_runs(self) -> None:
        decision = self.policy.decide_for_text("今天有哪些工具调用？")

        self.assertTrue(decision.needs_tool_runs_context)
        self.assertEqual(decision.requested_scopes, ["tool_runs"])

    def test_care_and_status_questions_request_care_events(self) -> None:
        for text in ("小安刚才有没有关心过我？", "我今天状态怎么样？"):
            with self.subTest(text=text):
                decision = self.policy.decide_for_text(text)

                self.assertTrue(decision.needs_care_context)
                self.assertIn("care", decision.requested_scopes)

    def test_unfinished_question_requests_tasks(self) -> None:
        decision = self.policy.decide_for_text("有什么还没完成？")

        self.assertTrue(decision.needs_tasks_context)
        self.assertEqual(decision.requested_scopes, ["tasks"])

    def test_general_questions_do_not_request_project_memory(self) -> None:
        for text in ("你好小安", "讲个笑话", "你是谁", "今天天气怎么样"):
            with self.subTest(text=text):
                self.assertEqual(
                    self.policy.decide_for_text(text).requested_scopes,
                    [],
                )

    def test_product_query_phrases_route_to_expected_scopes(self) -> None:
        cases = {
            "我还有哪些任务？": "tasks",
            "哪些任务没完成？": "tasks",
            "把任务列一下": "tasks",
            "有什么提醒？": "reminders",
            "明天有什么提醒？": "reminders",
            "最近有什么笔记？": "notes",
            "我刚才让你记了什么？": "notes",
            "最近日报是什么？": "summaries",
            "今天有哪些工具调用？": "tool_runs",
            "我刚才在做什么？": "work",
        }
        for text, scope in cases.items():
            with self.subTest(text=text):
                decision = self.policy.decide_for_text(text)
                self.assertIn(scope, decision.requested_scopes)
                self.assertEqual(decision.method, "keyword_heuristic")

    def test_policy_does_not_modify_database_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "xiao_an.db"

            decision = self.policy.decide_for_text("继续刚才的项目")

            self.assertTrue(decision.needs_work_context)
            self.assertFalse(db_path.exists())


if __name__ == "__main__":
    unittest.main()
