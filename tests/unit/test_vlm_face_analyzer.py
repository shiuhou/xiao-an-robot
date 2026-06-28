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

    def test_parses_extended_visible_evidence_contract(self) -> None:
        raw = (
            '{"polarity":"负面","emotion":"tired","emotion_score":0.6,'
            '"fatigue_score":0.8,"confidence":0.9,'
            '"visible_evidence":["眼皮偏沉","头部低垂"],'
            '"valid_observation":true,'
            '"message":"我注意到你的眼皮有些沉，要不要先休息一下？"}'
        )

        result = vfa._parse(raw)

        self.assertEqual(result["emotion_score"], 0.6)
        self.assertEqual(result["visible_evidence"], ["眼皮偏沉", "头部低垂"])
        self.assertEqual(result["valid_observation"], True)

    def test_invalid_output_is_safe_positive(self) -> None:
        result = vfa._parse("not json")

        self.assertEqual(result["polarity"], "正面")
        self.assertEqual(result["fatigue_score"], 0.0)
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["message"], "")

    def test_prompt_uses_human_friendly_visible_evidence_message(self) -> None:
        self.assertIn("我注意到", vfa.PROMPT)
        self.assertIn("可见面部/姿态线索", vfa.PROMPT)
        self.assertIn("visible_evidence", vfa.PROMPT)
        self.assertIn("valid_observation", vfa.PROMPT)
        self.assertIn("不要做医学诊断", vfa.PROMPT)

    def test_load_prompt_falls_back_when_file_missing(self) -> None:
        self.assertEqual(vfa._load_prompt(vfa._DEFAULT_PROMPT_FILE.with_name("missing-prompt.txt")), vfa._FALLBACK_PROMPT)

    def test_predict_does_not_emit_face_found_when_detection_was_not_run(self) -> None:
        analyzer = object.__new__(vfa.VLMFaceAnalyzer)
        analyzer.analyze_frame = MagicMock(return_value={
            "polarity": "正面",
            "emotion": "neutral",
            "emotion_score": 0.2,
            "fatigue_score": 0.1,
            "confidence": 0.8,
            "message": "",
            "visible_evidence": [],
            "valid_observation": True,
        })

        sample = analyzer.predict({"source": "manual", "frame_id": 1, "timestamp_ms": 123, "payload": object()})

        self.assertNotIn("face_found", sample)

    def test_predict_preserves_face_found_when_detection_was_run(self) -> None:
        analyzer = object.__new__(vfa.VLMFaceAnalyzer)
        analyzer.analyze_frame = MagicMock(return_value={
            "polarity": "正面",
            "emotion": "neutral",
            "emotion_score": 0.2,
            "fatigue_score": 0.1,
            "confidence": 0.8,
            "message": "",
            "visible_evidence": [],
            "valid_observation": True,
            "face_found": True,
        })

        sample = analyzer.predict({"source": "manual", "frame_id": 1, "timestamp_ms": 123, "payload": object()})

        self.assertEqual(sample["face_found"], True)

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
