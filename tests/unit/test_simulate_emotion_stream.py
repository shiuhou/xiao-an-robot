"""Unit tests for tools.simulate_emotion_stream pattern generation."""

from __future__ import annotations

import unittest

from tools.simulate_emotion_stream import build_sample, generate_samples


class SimulateEmotionStreamTest(unittest.TestCase):
    def test_tired_pattern_generates_tired_samples(self) -> None:
        samples = generate_samples("tired", 2)

        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0]["emotion_tag"], "tired")
        self.assertEqual(samples[0]["confidence"], 0.9)
        self.assertEqual(samples[0]["fatigue_score"], 0.85)
        self.assertEqual(samples[0]["seq"], 1)
        self.assertEqual(samples[1]["seq"], 2)

    def test_mixed_pattern_cycles_expected_emotions(self) -> None:
        samples = generate_samples("mixed", 6)

        self.assertEqual(
            [sample["emotion_tag"] for sample in samples],
            ["neutral", "tired", "tired", "neutral", "anxious", "neutral"],
        )

    def test_build_sample_uses_neutral_values(self) -> None:
        sample = build_sample("neutral", 0)

        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["confidence"], 0.5)
        self.assertEqual(sample["fatigue_score"], 0.2)


if __name__ == "__main__":
    unittest.main()
