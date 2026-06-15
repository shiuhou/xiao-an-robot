"""Unit tests for base_station.perception.valence_mapping (P0-4)."""

from __future__ import annotations

import unittest

from base_station.perception import valence_mapping as vm
from base_station.perception.vlm_trigger_gate import NEGATIVE_EMOTIONS


class ValenceMappingTest(unittest.TestCase):
    def test_all_eight_labels_have_concrete_valence(self) -> None:
        for label in vm.EXPRESSION_LABELS:
            self.assertIn(vm.classify_valence(label), {"positive", "negative", "neutral"})

    def test_unknown_label_is_uncertain(self) -> None:
        self.assertEqual(vm.classify_valence("Bored"), "uncertain")

    def test_negative_labels_map_to_negative_and_negative_polarity(self) -> None:
        for label in ["Sad", "Fear", "Disgust", "Anger", "Contempt"]:
            self.assertEqual(vm.classify_valence(label), "negative")
            self.assertTrue(vm.is_negative(label))
            self.assertEqual(vm.label_to_polarity(label), "负面")

    def test_positive_and_neutral_labels(self) -> None:
        self.assertEqual(vm.classify_valence("Happy"), "positive")
        self.assertEqual(vm.label_to_polarity("Happy"), "正面")
        self.assertEqual(vm.classify_valence("Neutral"), "neutral")
        self.assertEqual(vm.classify_valence("Surprise"), "neutral")
        self.assertEqual(vm.label_to_polarity("Surprise"), "正面")

    def test_uncertain_polarity_is_conservative(self) -> None:
        self.assertEqual(vm.valence_to_polarity("uncertain"), "正面")

    def test_gate_tag_maps_negatives_into_legacy_vocabulary(self) -> None:
        # The UNCHANGED VLMTriggerGate must still fire on OpenFace negative labels.
        for label in ["Sad", "Fear", "Anger", "Disgust", "Contempt"]:
            self.assertIn(vm.to_gate_emotion_tag(label), NEGATIVE_EMOTIONS)

    def test_gate_tag_for_non_negative_is_not_in_negative_set(self) -> None:
        for label in ["Neutral", "Happy", "Surprise"]:
            self.assertNotIn(vm.to_gate_emotion_tag(label), NEGATIVE_EMOTIONS)


if __name__ == "__main__":
    unittest.main()
