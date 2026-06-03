"""Unit tests for tools.simulate_emotion_stream pattern generation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from base_station.monitor.emotion_db import EmotionDB
from tools.simulate_emotion_stream import build_sample, generate_samples, simulation_db_path


class SimulateEmotionStreamTest(unittest.TestCase):
    def test_tired_pattern_generates_tired_samples(self) -> None:
        samples = generate_samples("tired", 2)

        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0]["emotion_tag"], "tired")
        self.assertEqual(samples[0]["source"], "fake_face")
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

    def test_fresh_db_ignores_polluted_fixed_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixed_db_path = str(Path(temp_dir) / "polluted.db")
            with EmotionDB(fixed_db_path) as fixed_db:
                for _ in range(5):
                    fixed_db.insert_emotion("face", "tired", 0.9, 0.85)
                self.assertEqual(fixed_db.get_recent_summary()["count"], 5)

            with simulation_db_path(fixed_db_path, fresh_db=True) as fresh_db_path:
                self.assertNotEqual(fresh_db_path, fixed_db_path)
                with EmotionDB(fresh_db_path) as fresh_db:
                    summary = fresh_db.get_recent_summary()

                self.assertEqual(summary["count"], 0)
                self.assertEqual(summary["avg_fatigue_score"], 0.0)
                self.assertEqual(summary["emotions_count"], {})

            self.assertFalse(Path(fresh_db_path).exists())


if __name__ == "__main__":
    unittest.main()
