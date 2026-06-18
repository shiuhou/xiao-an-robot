"""Unit tests for VLMTriggerGate."""

from __future__ import annotations

import unittest

from base_station.perception.vlm_trigger_gate import VLMTriggerGate


class VLMTriggerGateTest(unittest.TestCase):
    def test_neutral_does_not_trigger(self) -> None:
        gate = VLMTriggerGate()

        result = gate.evaluate({
            "emotion_tag": "neutral",
            "confidence": 0.9,
            "fatigue_score": 0.1,
        })

        self.assertEqual(result, {"should_trigger": False, "reason": "normal"})

    def test_high_fatigue_uses_openface_score_scale_by_default(self) -> None:
        gate = VLMTriggerGate()

        below_threshold = gate.evaluate({
            "emotion_tag": "neutral",
            "confidence": 0.2,
            "fatigue_score": 66,
        })
        at_threshold = gate.evaluate({
            "emotion_tag": "neutral",
            "confidence": 0.2,
            "fatigue_score": 67,
        })

        self.assertEqual(below_threshold, {"should_trigger": False, "reason": "normal"})
        self.assertEqual(at_threshold, {"should_trigger": True, "reason": "high_fatigue"})

    def test_negative_emotions_with_high_confidence_trigger(self) -> None:
        for emotion_tag in ["sad", "anxious", "tired", "stressed"]:
            with self.subTest(emotion_tag=emotion_tag):
                gate = VLMTriggerGate()

                result = gate.evaluate({
                    "emotion_tag": emotion_tag,
                    "confidence": 0.8,
                    "fatigue_score": 0.1,
                })

                self.assertEqual(result, {"should_trigger": True, "reason": "negative_emotion"})

    def test_low_confidence_negative_emotion_does_not_trigger(self) -> None:
        gate = VLMTriggerGate()

        result = gate.evaluate({
            "emotion_tag": "sad",
            "confidence": 0.3,
            "fatigue_score": 0.1,
        })

        self.assertEqual(result, {"should_trigger": False, "reason": "normal"})

    def test_consecutive_negative_emotions_trigger_window(self) -> None:
        gate = VLMTriggerGate(negative_count_threshold=2)

        first = gate.evaluate({
            "emotion_tag": "sad",
            "confidence": 0.5,
            "fatigue_score": 0.1,
        })
        second = gate.evaluate({
            "emotion_tag": "anxious",
            "confidence": 0.5,
            "fatigue_score": 0.1,
        })

        self.assertEqual(first, {"should_trigger": False, "reason": "normal"})
        self.assertEqual(second, {"should_trigger": True, "reason": "negative_emotion_window"})

    def test_negative_emotion_window_counts_negative_history(self) -> None:
        gate = VLMTriggerGate(negative_confidence_threshold=0.95, negative_count_threshold=2)

        gate.evaluate({"emotion_tag": "sad", "confidence": 0.5, "fatigue_score": 0.1})
        result = gate.evaluate({"emotion_tag": "anxious", "confidence": 0.5, "fatigue_score": 0.1})

        self.assertEqual(result, {"should_trigger": True, "reason": "negative_emotion_window"})

    def test_force_vlm_triggers_force(self) -> None:
        gate = VLMTriggerGate()

        result = gate.evaluate({}, force_vlm=True)

        self.assertEqual(result, {"should_trigger": True, "reason": "force"})

    def test_missing_fields_do_not_raise(self) -> None:
        gate = VLMTriggerGate()

        result = gate.evaluate({})

        self.assertEqual(result, {"should_trigger": False, "reason": "normal"})

    def test_unknown_emotion_is_not_negative(self) -> None:
        gate = VLMTriggerGate()

        result = gate.evaluate({
            "emotion_tag": "confused",
            "confidence": 0.99,
            "fatigue_score": 0.1,
        })

        self.assertEqual(result, {"should_trigger": False, "reason": "normal"})

    def test_window_size_limits_history_length(self) -> None:
        gate = VLMTriggerGate(
            negative_confidence_threshold=0.95,
            window_size=2,
            negative_count_threshold=2,
        )

        gate.evaluate({"emotion_tag": "sad", "confidence": 0.96})
        gate.evaluate({"emotion_tag": "neutral", "confidence": 0.9})
        result = gate.evaluate({"emotion_tag": "happy", "confidence": 0.9})

        self.assertEqual(result, {"should_trigger": False, "reason": "normal"})
        self.assertEqual(len(gate._recent_negative_flags), 2)

    def test_custom_thresholds_are_used(self) -> None:
        gate = VLMTriggerGate(
            fatigue_threshold=0.6,
            negative_confidence_threshold=0.4,
        )

        fatigue_result = gate.evaluate({
            "emotion_tag": "neutral",
            "confidence": 0.1,
            "fatigue_score": 0.65,
        })
        emotion_result = gate.evaluate({
            "emotion_tag": "sad",
            "confidence": 0.45,
            "fatigue_score": 0.1,
        })

        self.assertEqual(fatigue_result, {"should_trigger": True, "reason": "high_fatigue"})
        self.assertEqual(emotion_result, {"should_trigger": True, "reason": "negative_emotion"})


if __name__ == "__main__":
    unittest.main()
