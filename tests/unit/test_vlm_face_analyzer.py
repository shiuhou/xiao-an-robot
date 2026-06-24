"""Unit tests for VLMFaceAnalyzer parsing and optional imports."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

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

    def test_context_prompt_includes_safe_context_without_au_json(self) -> None:
        prompt = vfa._context_prompt({
            "cv": {
                "emotion_tag": "tired",
                "confidence": 0.8,
                "au_json": {"AU45": 0.9},
            },
            "asr": {"text": ""},
            "history": {"count": 2, "top_emotion": "tired"},
        })

        self.assertIn("Auxiliary context", prompt)
        self.assertIn('"emotion_tag": "tired"', prompt)
        self.assertIn('"top_emotion": "tired"', prompt)
        self.assertNotIn("au_json", prompt)

    def test_context_prompt_truncates_long_context(self) -> None:
        prompt = vfa._context_prompt({"cv": {"emotion_tag": "tired", "notes": "x" * 4000}})

        self.assertIn("...<truncated>", prompt)
        self.assertLessEqual(len(prompt), vfa.MAX_CONTEXT_PROMPT_CHARS + 220)

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

    def test_processor_loads_with_mistral_regex_fix(self) -> None:
        cv2 = types.ModuleType("cv2")
        cv2.data = types.SimpleNamespace(haarcascades="")
        cv2.CascadeClassifier = MagicMock(return_value=object())

        auto_processor = MagicMock()
        auto_processor.from_pretrained = MagicMock(return_value=object())
        transformers = types.ModuleType("transformers")
        transformers.AutoProcessor = auto_processor

        ov_model = MagicMock()
        ov_model.from_pretrained = MagicMock(return_value=object())
        optimum = types.ModuleType("optimum")
        optimum_intel = types.ModuleType("optimum.intel")
        optimum_intel.OVModelForVisualCausalLM = ov_model

        with tempfile.TemporaryDirectory() as model_dir:
            with patch.dict(
                sys.modules,
                {
                    "cv2": cv2,
                    "transformers": transformers,
                    "optimum": optimum,
                    "optimum.intel": optimum_intel,
                    "qwen_vl_utils": types.ModuleType("qwen_vl_utils"),
                    "PIL": types.ModuleType("PIL"),
                },
            ):
                vfa.VLMFaceAnalyzer(model_dir=model_dir)

        auto_processor.from_pretrained.assert_called_once_with(
            model_dir,
            max_pixels=vfa.MAX_PIXELS,
            fix_mistral_regex=True,
        )


if __name__ == "__main__":
    unittest.main()
