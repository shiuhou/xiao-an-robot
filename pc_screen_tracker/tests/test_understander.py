"""L3 optimization tests (ARCHITECTURE §14): task_closed actually closes a
task, and task state can persist across process restarts.

Found during the loop: `task_closed` was in the model's required-field JSON
schema and validated (`_REQUIRED`), but never applied anywhere — a task the
model marked done stayed "active" forever (until the 30-min idle timeout),
so an unrelated later segment could get misassociated onto it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tracker.segmenter import Segment
from tracker.understander import (
    QwenUnderstander, RuleUnderstander, _Task, _TaskState, make_understander,
)


def seg(seg_id=1, start_ms=0, end_ms=5000, app="chrome.exe", title="A",
        content=None) -> Segment:
    return Segment(
        seg_id=seg_id, start_ms=start_ms, end_ms=end_ms, app=app, title=title,
        kind="browser_page", capture_policy="full", content=content or ["hello world"],
    )


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, payload: dict):
        self._payload = payload

    def create(self, **kwargs):
        return _FakeResponse(json.dumps(self._payload, ensure_ascii=False))


class _FakeChat:
    def __init__(self, payload: dict):
        self.completions = _FakeCompletions(payload)


class _FakeClient:
    def __init__(self, payload: dict):
        self.chat = _FakeChat(payload)


def _qwen_with_fake_response(payload: dict) -> QwenUnderstander:
    u = QwenUnderstander(api_key="fake-key-not-used")
    u.client = _FakeClient(payload)
    return u


class TestTaskClosedApplied(unittest.TestCase):
    def test_task_closed_true_removes_task_from_active(self):
        u = _qwen_with_fake_response({
            "continues_project_id": "NEW", "new_task_title": "写周报",
            "activity_type": "writing", "gist": "在写周报",
            "confidence": 0.9, "task_closed": True,
        })
        note = u.ingest(seg())
        active = u.state.active(now_ms=5000)
        self.assertEqual(len(active), 0, "task marked closed must not stay active")
        self.assertEqual(note.project_hint, "写周报")

    def test_task_closed_false_keeps_task_active(self):
        u = _qwen_with_fake_response({
            "continues_project_id": "NEW", "new_task_title": "调研港科广",
            "activity_type": "researching", "gist": "在搜港科广",
            "confidence": 0.9, "task_closed": False,
        })
        u.ingest(seg())
        active = u.state.active(now_ms=5000)
        self.assertEqual(len(active), 1)

    def test_closed_task_not_offered_for_continuation(self):
        # first segment opens+closes a task; a later unrelated segment must
        # NOT see it in active_tasks (so the model can't misassociate onto it)
        u = _qwen_with_fake_response({
            "continues_project_id": "NEW", "new_task_title": "写周报",
            "activity_type": "writing", "gist": "在写周报",
            "confidence": 0.9, "task_closed": True,
        })
        u.ingest(seg(seg_id=1, start_ms=0, end_ms=5000))
        payload = u._payload(seg(seg_id=2, start_ms=6000, end_ms=9000))
        self.assertEqual(payload["active_tasks"], [])

    def test_closed_task_cannot_be_revived_by_stale_pid(self):
        # §14 L3 review fix: even if the model echoes a CLOSED task's id
        # (JSON mode guesses "t_001" when active_tasks is empty), an unrelated
        # segment must open a NEW task, not inherit the finished task's title
        # or silently re-open it.
        u = _qwen_with_fake_response({
            "continues_project_id": "NEW", "new_task_title": "写周报",
            "activity_type": "writing", "gist": "在写周报",
            "confidence": 0.9, "task_closed": True,
        })
        u.ingest(seg(seg_id=1, start_ms=0, end_ms=5000))

        # model now (incorrectly) claims continuation of the closed t_001
        u.client = _FakeClient({
            "continues_project_id": "t_001", "new_task_title": "读代码",
            "activity_type": "coding", "gist": "在读一段无关代码",
            "confidence": 0.9, "task_closed": False,
        })
        note = u.ingest(seg(seg_id=2, start_ms=6000, end_ms=9000))

        self.assertNotEqual(note.project_id, "t_001")
        self.assertEqual(note.project_hint, "读代码")
        self.assertTrue(u.state.get("t_001").closed, "closed task must stay closed")


class TestTaskStateFilter(unittest.TestCase):
    def test_active_excludes_closed_even_if_recently_touched(self):
        state = _TaskState()
        t = state.new("任务A", "working", seg(end_ms=1000))
        t.closed = True
        self.assertEqual(state.active(now_ms=1000), [])


class TestPersistence(unittest.TestCase):
    def test_save_load_roundtrip_preserves_tasks_and_closed_flags(self):
        state = _TaskState()
        t1 = state.new("任务A", "coding", seg(end_ms=1000))
        t1.touch(seg(end_ms=2000), "写了点代码", "coding")
        t2 = state.new("任务B", "writing", seg(end_ms=3000))
        t2.closed = True

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "task_state.json")
            state.save(path)

            fresh = _TaskState()
            loaded = fresh.load(path)
            self.assertTrue(loaded)
            self.assertEqual(fresh._n, 2)
            active = fresh.active(now_ms=2000)
            self.assertEqual(len(active), 1)  # t2 stays excluded (closed)
            self.assertEqual(active[0].title, "任务A")
            self.assertEqual(active[0].trace[-1]["gist"], "写了点代码")

    def test_load_missing_file_returns_false_and_keeps_state_empty(self):
        state = _TaskState()
        loaded = state.load("/nonexistent/path/task_state.json")
        self.assertFalse(loaded)
        self.assertEqual(state.active(now_ms=0), [])

    def test_make_understander_state_path_restores_task_across_instances(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")

            u1 = make_understander("rule", state_path=path)
            u1.ingest(seg(app="chrome.exe", title="A"))
            u1.state.save(path)
            first_pid = u1.state.active(now_ms=5000)[0].project_id

            u2 = make_understander("rule", state_path=path)
            active = u2.state.active(now_ms=5000)
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0].project_id, first_pid)
            # continuing the SAME app must reuse the restored task, not t_001 reset
            note = u2.ingest(seg(app="chrome.exe", title="A", start_ms=6000, end_ms=7000))
            self.assertEqual(note.project_id, first_pid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
