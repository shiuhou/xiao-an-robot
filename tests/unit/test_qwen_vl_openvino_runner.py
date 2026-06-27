"""Unit tests for Qwen VL OpenVINO runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_load_missing_model_dir_raises_clear_error(self) -> None:
        runner = QwenVLOpenVINORunner(model_dir="models/qwen")

        with self.assertRaisesRegex(FileNotFoundError, "Qwen2.5-VL OpenVINO model directory"):
            runner.load()

    def test_generate_empty_prompt_raises_value_error(self) -> None:
        runner = QwenVLOpenVINORunner(model_dir="models/qwen")

        with self.assertRaisesRegex(ValueError, "prompt"):
            runner.generate(image="image", prompt="   ")

    def test_load_missing_dependencies_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "openvino_model.xml").write_text("<xml />", encoding="utf-8")
            Path(temp_dir, "openvino_model.bin").write_bytes(b"bin")
            runner = QwenVLOpenVINORunner(model_dir=temp_dir)

            with patch(
                "base_station.perception.qwen_vl_openvino_runner.import_module",
                side_effect=ImportError("missing"),
            ):
                with self.assertRaisesRegex(ImportError, "missing package"):
                    runner.load()

    def test_load_empty_model_dir_raises_format_error_before_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = QwenVLOpenVINORunner(model_dir=temp_dir)

            with self.assertRaisesRegex(RuntimeError, "format mismatch"):
                runner.load()

    def test_model_dir_expands_user_home(self) -> None:
        runner = QwenVLOpenVINORunner(model_dir="~/models/Qwen2.5-VL-3B-OV-int4")

        self.assertNotIn("~", runner.model_dir)

    def test_generate_valid_prompt_reports_missing_model_dir_not_not_implemented(self) -> None:
        runner = QwenVLOpenVINORunner(model_dir="models/qwen")

        with self.assertRaisesRegex(FileNotFoundError, "model directory"):
            runner.generate(image="image", prompt="Analyze emotion.")

    def test_model_path_file_raises_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "model.xml"
            path.write_text("<xml />", encoding="utf-8")
            runner = QwenVLOpenVINORunner(model_dir=str(path))

            with self.assertRaisesRegex(RuntimeError, "not a directory"):
                runner.load()

    def test_build_emotion_analysis_prompt_returns_string(self) -> None:
        prompt = build_emotion_analysis_prompt()

        self.assertIsInstance(prompt, str)

    def test_prompt_contains_json_output_requirement(self) -> None:
        prompt = build_emotion_analysis_prompt()

        self.assertIn("Return JSON only", prompt)
        self.assertIn("Output JSON only", prompt)
        self.assertIn("Do not include markdown fences", prompt)
        self.assertIn("Do not include explanation outside JSON", prompt)
        self.assertIn("required keys", prompt)
        self.assertIn("emotion_tag", prompt)
        self.assertIn("confidence", prompt)
        self.assertIn("fatigue_score", prompt)
        self.assertIn("visual_reason", prompt)
        self.assertIn("vlm_observation", prompt)
        self.assertIn("confidence below 0.5", prompt)

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
