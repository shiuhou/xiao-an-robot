"""Unit tests for local OpenClaw placeholder tools."""

from __future__ import annotations

import unittest

from agent.core.local_tools import LocalToolRegistry


class LocalToolRegistryTest(unittest.TestCase):
    def test_note_add_returns_placeholder_result(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("note.add", {"content": "记一下", "tags": ["work"]})

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "note.add")
        self.assertEqual(result["result"]["content"], "记一下")
        self.assertEqual(result["result"]["tags"], ["work"])

    def test_work_context_record_returns_placeholder_result(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("work_context.record", {"content": "写项目代码", "source": "frontend"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "work_context.record")
        self.assertEqual(result["result"]["content"], "写项目代码")
        self.assertEqual(result["result"]["source"], "frontend")

    def test_summary_daily_returns_placeholder_status(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("summary.daily", {"date": "2026-06-13"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "summary.daily")
        self.assertEqual(result["result"]["date"], "2026-06-13")
        self.assertEqual(result["result"]["status"], "placeholder")

    def test_none_arguments_do_not_crash(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("note.add", None)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["content"], "")
        self.assertEqual(result["result"]["tags"], [])

    def test_unknown_tool_returns_ok_false(self) -> None:
        registry = LocalToolRegistry()

        result = registry.execute("unknown.tool", {"x": 1})

        self.assertFalse(result["ok"])
        self.assertEqual(result["name"], "unknown.tool")
        self.assertEqual(result["error"], "unsupported local tool")


if __name__ == "__main__":
    unittest.main()
