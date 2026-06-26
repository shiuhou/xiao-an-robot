"""Unit tests for ASR emotion keyword triggers."""

from __future__ import annotations

import unittest

from base_station.perception.asr_emotion_trigger import ASREmotionTrigger, detect_asr_emotion_trigger


class ASREmotionTriggerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.trigger = ASREmotionTrigger()

    def test_fatigue_keyword_triggers_for_tired_text(self) -> None:
        result = self.trigger.analyze("我有点累")

        self.assertEqual(result["should_trigger"], True)
        self.assertEqual(result["reason"], "fatigue_keyword")
        self.assertEqual(result["matched_keyword"], "累")
        self.assertEqual(result["emotion_tag"], "tired")
        self.assertEqual(result["confidence"], 0.75)
        self.assertEqual(result["fatigue_score"], 0.8)

    def test_negative_keyword_triggers_for_annoyed_text(self) -> None:
        result = self.trigger.analyze("我今天好烦")

        self.assertEqual(result["should_trigger"], True)
        self.assertEqual(result["reason"], "negative_keyword")
        self.assertEqual(result["matched_keyword"], "烦")
        self.assertEqual(result["emotion_tag"], "stressed")
        self.assertEqual(result["confidence"], 0.7)
        self.assertEqual(result["fatigue_score"], 0.5)

    def test_normal_text_does_not_trigger(self) -> None:
        result = self.trigger.analyze("帮我查一下天气")

        self.assertEqual(result["should_trigger"], False)
        self.assertEqual(result["reason"], "normal")
        self.assertIsNone(result["matched_keyword"])
        self.assertEqual(result["emotion_tag"], "neutral")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["fatigue_score"], 0.0)

    def test_empty_inputs_do_not_trigger(self) -> None:
        for text in ("", None, "   "):
            with self.subTest(text=text):
                result = self.trigger.analyze(text)

                self.assertEqual(result["should_trigger"], False)
                self.assertEqual(result["reason"], "normal")
                self.assertIsNone(result["matched_keyword"])

    def test_rest_phrase_triggers_fatigue_keyword(self) -> None:
        result = self.trigger.analyze("我想休息一下")

        self.assertEqual(result["should_trigger"], True)
        self.assertEqual(result["reason"], "fatigue_keyword")
        self.assertEqual(result["matched_keyword"], "休息一下")

    def test_lowercase_emo_triggers_negative_keyword(self) -> None:
        result = self.trigger.analyze("emo 了")

        self.assertEqual(result["should_trigger"], True)
        self.assertEqual(result["reason"], "negative_keyword")
        self.assertEqual(result["matched_keyword"], "emo")

    def test_companion_phrase_triggers_negative_keyword(self) -> None:
        result = self.trigger.analyze("陪陪我")

        self.assertEqual(result["should_trigger"], True)
        self.assertEqual(result["reason"], "negative_keyword")
        self.assertEqual(result["matched_keyword"], "陪陪我")

    def test_breakdown_phrase_triggers_negative_keyword(self) -> None:
        result = self.trigger.analyze("我有点崩溃")

        self.assertEqual(result["should_trigger"], True)
        self.assertEqual(result["reason"], "negative_keyword")
        self.assertEqual(result["matched_keyword"], "崩溃")

    def test_uppercase_emo_triggers_negative_keyword(self) -> None:
        result = self.trigger.analyze("EMO 了")

        self.assertEqual(result["should_trigger"], True)
        self.assertEqual(result["reason"], "negative_keyword")
        self.assertEqual(result["matched_keyword"], "emo")

    def test_detect_asr_emotion_trigger_convenience_function(self) -> None:
        result = detect_asr_emotion_trigger("我今天压力大")

        self.assertEqual(result["should_trigger"], True)
        self.assertEqual(result["reason"], "negative_keyword")
        self.assertEqual(result["matched_keyword"], "压力大")


if __name__ == "__main__":
    unittest.main()
