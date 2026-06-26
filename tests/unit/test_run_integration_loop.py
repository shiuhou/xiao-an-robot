"""Tests for the one-task integration loop scheduler."""

from __future__ import annotations

import unittest

from pathlib import Path
import tempfile

from tools.run_integration_loop import load_queue, run_cycle, select_next_task


class IntegrationLoopTest(unittest.TestCase):
    def test_priority_queue_declares_policy_and_all_tasks(self) -> None:
        queue = load_queue("docs/agents/08_priority_queue.yaml")

        self.assertTrue(queue["policy"]["one_task_per_cycle"])
        self.assertTrue(queue["policy"]["select_highest_priority_ready"])
        self.assertEqual(queue["policy"]["max_fix_attempts"], 2)
        self.assertEqual([task["id"] for task in queue["tasks"]], [f"T{i:02d}" for i in range(17)])

    def test_selects_highest_priority_ready_task_with_satisfied_dependencies(self) -> None:
        queue = {
            "tasks": [
                {"id": "T00", "priority": "P0", "depends_on": [], "status": "PASS"},
                {"id": "T01", "priority": "P0", "depends_on": ["T00"], "status": "PASS"},
                {"id": "T02", "priority": "P0", "depends_on": ["T01"], "status": "READY"},
                {"id": "T03", "priority": "P0", "depends_on": ["T02"], "status": "READY"},
            ]
        }

        selected = select_next_task(queue, {"results": {}})

        self.assertEqual(selected["task"]["id"], "T02")
        self.assertEqual(selected["reason"], "ready")

    def test_active_waiting_task_blocks_next_selection(self) -> None:
        queue = {
            "tasks": [
                {"id": "T00", "priority": "P0", "depends_on": [], "status": "PASS"},
                {"id": "T01", "priority": "P0", "depends_on": ["T00"], "status": "READY"},
            ]
        }
        state = {
            "current_task": {
                "task_id": "T00",
                "status": "WAITING_HUMAN",
                "attempt": 1,
            },
            "results": {},
        }

        selected = select_next_task(queue, state)

        self.assertEqual(selected["task"]["id"], "T00")
        self.assertEqual(selected["reason"], "active_task")

    def test_skips_tasks_already_marked_pass_in_results(self) -> None:
        queue = {
            "tasks": [
                {"id": "T00", "priority": "P0", "depends_on": [], "status": "READY"},
                {"id": "T01", "priority": "P0", "depends_on": ["T00"], "status": "READY"},
            ]
        }
        state = {"results": {"T00": {"status": "PASS"}}}

        selected = select_next_task(queue, state)

        self.assertEqual(selected["task"]["id"], "T01")
        self.assertEqual(selected["reason"], "ready")

    def test_run_cycle_records_only_one_selected_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            state_path = Path(temp_dir) / "results.json"
            queue_path.write_text(
                """
{
  "policy": {
    "one_task_per_cycle": true,
    "select_highest_priority_ready": true,
    "max_fix_attempts": 2
  },
  "tasks": [
    {"id": "T00", "title": "First", "priority": "P0", "depends_on": [], "status": "READY"},
    {"id": "T01", "title": "Second", "priority": "P0", "depends_on": ["T00"], "status": "READY"}
  ]
}
""",
                encoding="utf-8",
            )

            result = run_cycle(queue_path, state_path, execute=False)

            self.assertEqual(result["selected"]["task"]["id"], "T00")
            self.assertEqual(result["selected"]["reason"], "ready")
            self.assertTrue(state_path.exists())
            state = state_path.read_text(encoding="utf-8")
            self.assertIn('"task_id": "T00"', state)
            self.assertNotIn('"task_id": "T01"', state)


if __name__ == "__main__":
    unittest.main()
