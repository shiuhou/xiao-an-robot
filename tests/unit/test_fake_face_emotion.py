"""Unit tests for FakeFaceEmotionSource."""

from __future__ import annotations

import unittest

from base_station.perception.fake_face_emotion import FakeFaceEmotionSource


async def collect_samples(source: FakeFaceEmotionSource) -> list[dict]:
    samples = []
    async for sample in source.samples():
        samples.append(sample)
    return samples


class FakeFaceEmotionSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_neutral_pattern_outputs_expected_sample(self) -> None:
        samples = await collect_samples(FakeFaceEmotionSource("neutral", count=1, interval_seconds=0))

        self.assertEqual(samples[0]["source"], "fake_face")
        self.assertEqual(samples[0]["emotion_tag"], "neutral")
        self.assertEqual(samples[0]["confidence"], 0.5)
        self.assertEqual(samples[0]["fatigue_score"], 0.2)

    async def test_tired_pattern_outputs_expected_sample(self) -> None:
        samples = await collect_samples(FakeFaceEmotionSource("tired", count=1, interval_seconds=0))

        self.assertEqual(samples[0]["emotion_tag"], "tired")
        self.assertEqual(samples[0]["confidence"], 0.9)
        self.assertEqual(samples[0]["fatigue_score"], 0.85)

    async def test_anxious_pattern_outputs_expected_sample(self) -> None:
        samples = await collect_samples(FakeFaceEmotionSource("anxious", count=1, interval_seconds=0))

        self.assertEqual(samples[0]["emotion_tag"], "anxious")
        self.assertEqual(samples[0]["confidence"], 0.88)
        self.assertEqual(samples[0]["fatigue_score"], 0.4)

    async def test_mixed_pattern_cycles_expected_order(self) -> None:
        samples = await collect_samples(FakeFaceEmotionSource("mixed", count=6, interval_seconds=0))

        self.assertEqual(
            [sample["emotion_tag"] for sample in samples],
            ["neutral", "tired", "tired", "neutral", "anxious", "neutral"],
        )

    async def test_count_limits_output(self) -> None:
        samples = await collect_samples(FakeFaceEmotionSource("tired", count=3, interval_seconds=0))

        self.assertEqual(len(samples), 3)

    async def test_output_contains_required_fields(self) -> None:
        samples = await collect_samples(FakeFaceEmotionSource("neutral", count=1, interval_seconds=0))

        self.assertEqual(set(samples[0]), {"source", "emotion_tag", "confidence", "fatigue_score"})
