"""Unit test for the ActivityNote -> work_activities mapping (phase 0).

Run from pc_screen_tracker/:
    python -m unittest tests.test_bridge
or directly:
    python tests/test_bridge.py
"""
from __future__ import annotations

import os
import sys
import unittest

# make `tracker` importable no matter the cwd
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tracker.bridge import note_to_kwargs, post_note, should_transport
from tracker.understander import ActivityNote


def _sample_note() -> ActivityNote:
    return ActivityNote(
        timestamp_ms=1720000000000,
        app_name="chrome.exe",
        window_title="xiao-an-robot - GitHub",
        activity_type="researching",
        project_id="t_001",                       # in-batch id — must NOT be stored
        project_hint="调研港科广小安机器人衔接层",
        gist="在 GitHub 上看 work_activities 表结构",
        confidence=0.82,
        duration_seconds=95,
    )


class TestNoteToKwargs(unittest.TestCase):
    def test_full_mapping_is_exact(self):
        kwargs = note_to_kwargs(_sample_note())
        self.assertEqual(
            kwargs,
            {
                "source": "screen",
                "app_name": "chrome.exe",
                "window_title": "xiao-an-robot - GitHub",
                "activity_type": "researching",
                "project_hint": "调研港科广小安机器人衔接层",
                "note": "在 GitHub 上看 work_activities 表结构",
                "confidence": 0.82,
                "duration_seconds": 95,
                "timestamp_ms": 1720000000000,
                "project_id": None,
            },
        )

    def test_string_project_id_is_dropped(self):
        # decision 3: our "t_001" must never land in the INTEGER column
        self.assertIsNone(note_to_kwargs(_sample_note())["project_id"])

    def test_gist_becomes_note(self):
        note = _sample_note()
        self.assertEqual(note_to_kwargs(note)["note"], note.gist)

    def test_empty_source_defaults_to_screen(self):
        note = _sample_note()
        note.source = ""
        self.assertEqual(note_to_kwargs(note)["source"], "screen")


class TestTransportRedLine(unittest.TestCase):
    def test_full_and_meta_only_are_transportable(self):
        note = _sample_note()
        note.capture_policy = "full"
        self.assertTrue(should_transport(note))
        note.capture_policy = "meta_only"
        self.assertTrue(should_transport(note))

    def test_sensitive_is_not_transportable(self):
        note = _sample_note()
        note.capture_policy = "none"
        self.assertFalse(should_transport(note))

    def test_post_note_drops_sensitive_before_any_network(self):
        note = _sample_note()
        note.capture_policy = "none"
        # unreachable URL on purpose: a sensitive note must be dropped BEFORE any
        # network call, so this returns instantly with no connection attempt.
        result = post_note(note, "http://127.0.0.1:9")
        self.assertFalse(result["posted"])
        self.assertEqual(result["reason"], "sensitive_not_transported")


if __name__ == "__main__":
    unittest.main(verbosity=2)
