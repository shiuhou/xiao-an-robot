"""Unit tests for VLMFaceAnalyzer parsing and optional imports."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from base_station.perception import vlm_face_analyzer as vfa


class VLMFaceAnalyzerParseTest(unittest.TestCase):
    def test_parses_positive_empty_message(self) -> None:
        raw = '{"polarity":"正面","emotion":"neutral","fatigue_score":0.1,"confidence":0.7,"message":""}'

        result = vfa._parse(raw)

        self.assertEqual(result["polarity"], "正面")
        self.assertEqual(result["emotion"], "neutral")
        self.assertEqual(result["message"], "")

    def test_parses_negative_message(self) -> None:
        raw = '{"polarity":"负面","emotion":"tired","fatigue_score":0.8,"confidence":0.9,"message":"先休息一下吧。"}'

        result = vfa._parse(raw)

        self.assertEqual(result["polarity"], "负面")
        self.assertEqual(result["emotion"], "tired")
        self.assertEqual(result["message"], "先休息一下吧。")

    def test_invalid_output_is_safe_positive(self) -> None:
        result = vfa._parse("not json")

        self.assertEqual(result["polarity"], "正面")
        self.assertEqual(result["fatigue_score"], 0.0)
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["message"], "")

    def test_prompt_allows_empty_positive_message_and_requires_negative_care(self) -> None:
        self.assertIn("正面或无需干预，必须为空字符串", vfa.PROMPT)
        self.assertIn("如果 polarity 是负面，生成一句自然简短的中文关怀话", vfa.PROMPT)

    def test_missing_model_dir_raises_before_heavy_imports(self) -> None:
        with patch.dict(
            sys.modules,
            {
                "cv2": None,
                "transformers": None,
                "optimum": None,
                "qwen_vl_utils": None,
                "PIL": None,
            },
        ):
            with self.assertRaisesRegex(FileNotFoundError, "VLM model not found"):
                vfa.VLMFaceAnalyzer(model_dir="missing-vlm-model")


if __name__ == "__main__":
    unittest.main()
