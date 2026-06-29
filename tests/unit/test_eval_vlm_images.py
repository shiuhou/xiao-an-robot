"""Unit tests for offline VLM image evaluation."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from tools import eval_vlm_images as evaluator


def _label(
    *,
    expected_visible_state: str = "neutral_visible",
    expected_care_state: str = "no_care",
    forbidden_claims: str = "fatigue_score; fatigue_level",
) -> dict[str, str]:
    return {
        "sample_id": "NEU01",
        "image_path": "images/NEU01.jpg",
        "expected_visible_state": expected_visible_state,
        "expected_care_state": expected_care_state,
        "forbidden_claims": forbidden_claims,
    }


def _raw(**overrides: object) -> str:
    data = {
        "executed": True,
        "status": "ok",
        "visible_state": "neutral_visible",
        "care_state": "no_care",
        "confidence": 0.8,
        "visible_evidence": ["face visible", "neutral mouth"],
        "message": "",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class EvalVLMImagesTest(unittest.TestCase):
    def test_filter_annotations_with_limit_two_processes_two_samples(self) -> None:
        annotations = [
            _label(expected_visible_state="neutral_visible") | {"sample_id": "NEU01"},
            _label(expected_visible_state="positive_visible") | {"sample_id": "POS01"},
            _label(expected_visible_state="fatigue_visible") | {"sample_id": "FAT01"},
        ]

        filtered = evaluator.filter_annotations(annotations, limit=2)

        self.assertEqual([row["sample_id"] for row in filtered], ["NEU01", "POS01"])

    def test_ensure_repo_root_on_path_adds_project_root_for_direct_script_runs(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        original_path = list(sys.path)
        try:
            sys.path = [item for item in sys.path if Path(item or ".").resolve() != repo_root]

            evaluator.ensure_repo_root_on_path()

            self.assertEqual(Path(sys.path[0]).resolve(), repo_root)
        finally:
            sys.path = original_path

    def test_correct_json_is_parseable_and_valid(self) -> None:
        parsed = evaluator.parse_vlm_output(_raw())
        validation = evaluator.validate_output(parsed.value, _label())

        self.assertTrue(parsed.ok)
        self.assertEqual(parsed.value["visible_state"], "neutral_visible")
        self.assertTrue(validation.required_fields_present)
        self.assertTrue(validation.enum_valid)
        self.assertFalse(validation.forbidden_claims_hit)

    def test_missing_required_field_fails(self) -> None:
        parsed = evaluator.parse_vlm_output(_raw(care_state=None))
        parsed.value.pop("care_state")
        validation = evaluator.validate_output(parsed.value, _label())

        self.assertFalse(validation.required_fields_present)

    def test_invalid_enum_fails(self) -> None:
        parsed = evaluator.parse_vlm_output(_raw(visible_state="sleepy"))
        validation = evaluator.validate_output(parsed.value, _label())

        self.assertFalse(validation.enum_valid)

    def test_forbidden_claims_hit_fails(self) -> None:
        parsed = evaluator.parse_vlm_output(_raw(message="fatigue_score is high"))
        validation = evaluator.validate_output(parsed.value, _label())

        self.assertTrue(validation.forbidden_claims_hit)

    def test_forbidden_claims_do_not_match_inside_normal_words(self) -> None:
        parsed = evaluator.parse_vlm_output(_raw(
            visible_evidence=["A person wearing glasses is visible."],
        ))
        validation = evaluator.validate_output(parsed.value, _label())

        self.assertFalse(validation.forbidden_claims_hit)

    def test_visible_state_and_care_state_comparison_logic(self) -> None:
        parsed = evaluator.parse_vlm_output(_raw(
            visible_state="fatigue_visible",
            care_state="needs_care",
            message="You look tired from visible signs.",
        ))
        validation = evaluator.validate_output(
            parsed.value,
            _label(expected_visible_state="fatigue_visible", expected_care_state="needs_care"),
        )

        self.assertTrue(validation.visible_state_match)
        self.assertTrue(validation.care_state_match)

        wrong = evaluator.validate_output(parsed.value, _label())
        self.assertFalse(wrong.visible_state_match)
        self.assertFalse(wrong.care_state_match)


if __name__ == "__main__":
    unittest.main()
