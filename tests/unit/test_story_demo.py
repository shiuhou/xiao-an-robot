from __future__ import annotations

import unittest

from base_station.integration_console.story_demo import (
    START_NODE_ID,
    advance_story_state,
    build_story_state,
    is_story_start_request,
    iter_story_demo_tts_texts,
    resolve_story_choice,
    story_state_summary,
)


class StoryDemoTest(unittest.TestCase):
    def test_story_starts_at_intro_with_two_choices(self) -> None:
        state = build_story_state()
        summary = story_state_summary(state)

        self.assertTrue(summary["active"])
        self.assertEqual(summary["current_node"]["id"], START_NODE_ID)
        self.assertEqual(len(summary["current_node"]["choices"]), 2)

    def test_story_choice_can_advance_by_label_or_alias(self) -> None:
        state = build_story_state()
        choice = resolve_story_choice(state, "我想检查蓝色齿轮")

        self.assertIsNotNone(choice)
        advanced = advance_story_state(state, choice)  # type: ignore[arg-type]

        self.assertTrue(advanced["active"])
        self.assertEqual(advanced["current_node"], "gear")
        self.assertIn("gear", advanced["history"])

    def test_story_tts_texts_include_all_nodes(self) -> None:
        items = iter_story_demo_tts_texts()

        self.assertGreaterEqual(len(items), 10)
        self.assertTrue(all(item["link"] == "story" for item in items))
        self.assertTrue(any(item["intent"] == "intro" for item in items))

    def test_story_start_keyword_requires_story_wording(self) -> None:
        self.assertTrue(is_story_start_request("小安，讲个故事"))
        self.assertTrue(is_story_start_request("开始故事模式"))
        self.assertFalse(is_story_start_request("小安你好"))


if __name__ == "__main__":
    unittest.main()
