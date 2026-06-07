"""Unit tests for Qwen VL OpenVINO runner placeholder."""

from __future__ import annotations

import unittest

from base_station.perception.qwen_vl_openvino_runner import (
    QwenVLOpenVINORunner,
    build_emotion_analysis_prompt,
)


class QwenVLOpenVINORunnerTest(unittest.TestCase):
    def test_runner_initialization_saves_configuration(self) -> None:
        runner = QwenVLOpenVINORunner(
            model_dir="models/qwen2_5_vl_3b_openvino",
            device="GPU",
            max_new_tokens=64,
        )

        self.assertEqual(runner.model_dir, "models/qwen2_5_vl_3b_openvino")
        self.assertEqual(runner.device, "GPU")
        self.assertEqual(runner.max_new_tokens, 64)

    def test_empty_model_dir_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "model_dir"):
            QwenVLOpenVINORunner(model_dir="")

    def test_non_positive_max_new_tokens_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_new_tokens"):
            QwenVLOpenVINORunner(model_dir="models/qwen", max_new_tokens=0)

    def test_load_raises_not_implemented_with_openvino_hint(self) -> None:
        runner = QwenVLOpenVINORunner(model_dir="models/qwen")

        with self.assertRaisesRegex(NotImplementedError, "OpenVINO|Optimum Intel"):
            runner.load()

    def test_generate_empty_prompt_raises_value_error(self) -> None:
        runner = QwenVLOpenVINORunner(model_dir="models/qwen")

        with self.assertRaisesRegex(ValueError, "prompt"):
            runner.generate(image="image", prompt="   ")

    def test_generate_valid_prompt_raises_not_implemented(self) -> None:
        runner = QwenVLOpenVINORunner(model_dir="models/qwen")

        with self.assertRaisesRegex(NotImplementedError, "not implemented"):
            runner.generate(image="image", prompt="Analyze emotion.")

    def test_build_emotion_analysis_prompt_returns_string(self) -> None:
        prompt = build_emotion_analysis_prompt()

        self.assertIsInstance(prompt, str)

    def test_prompt_contains_json_output_requirement(self) -> None:
        prompt = build_emotion_analysis_prompt()

        self.assertIn("Return JSON only", prompt)
        self.assertIn("emotion_tag", prompt)
        self.assertIn("confidence", prompt)
        self.assertIn("fatigue_score", prompt)
        self.assertIn("visual_reason", prompt)
        self.assertIn("vlm_observation", prompt)

    def test_prompt_contains_allowed_emotion_tags(self) -> None:
        prompt = build_emotion_analysis_prompt()

        for emotion_tag in ["neutral", "tired", "sad", "anxious", "stressed", "happy", "unknown"]:
            self.assertIn(emotion_tag, prompt)

    def test_prompt_with_context_contains_key_information(self) -> None:
        prompt = build_emotion_analysis_prompt({
            "cv": {
                "emotion_tag": "tired",
                "fatigue_score": 0.85,
            },
            "asr": {
                "text": "我有点累",
            },
            "history": {
                "count": 3,
                "top_emotion": "tired",
            },
        })

        self.assertIn("cv:", prompt)
        self.assertIn("asr:", prompt)
        self.assertIn("history:", prompt)
        self.assertIn("tired", prompt)
        self.assertIn("我有点累", prompt)
        self.assertIn("0.85", prompt)


if __name__ == "__main__":
    unittest.main()
