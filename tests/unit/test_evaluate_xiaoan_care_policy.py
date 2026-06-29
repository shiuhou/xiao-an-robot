import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import evaluate_xiaoan_care_policy as policy


IMAGE_COLUMNS = [
    "image_id",
    "file_path",
    "subject_id",
    "scene",
    "light",
    "face_angle",
    "face_visible",
    "image_quality",
    "eye_state",
    "mouth_state",
    "head_pose",
    "affect_label",
    "fatigue_label",
    "care_needed",
    "care_action",
    "visible_evidence",
    "note",
]

ROI_COLUMNS = [
    "image_id",
    "file_path",
    "roi_path",
    "status",
    "x1",
    "y1",
    "x2",
    "y2",
    "detector",
    "note",
]


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def touch(root, relative_path):
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake")


def image_row(image_id, scene, fatigue, affect, care_needed="0", face_visible="yes", image_quality="good"):
    return {
        "image_id": image_id,
        "file_path": f"raw/images/{image_id}.jpg",
        "subject_id": "s01",
        "scene": scene,
        "light": "normal",
        "face_angle": "front",
        "face_visible": face_visible,
        "image_quality": image_quality,
        "eye_state": "unknown",
        "mouth_state": "unknown",
        "head_pose": "front",
        "affect_label": affect,
        "fatigue_label": fatigue,
        "care_needed": care_needed,
        "care_action": "",
        "visible_evidence": "",
        "note": "",
    }


def make_dataset(root):
    rows = [
        image_row("s01_severe_sleepy_normal_front_0001", "severe_sleepy", "severe", "neutral", "1"),
        image_row("s01_normal_focus_normal_front_0001", "normal_focus", "none", "neutral", "0"),
        image_row("s01_mild_fatigue_normal_front_0001", "mild_fatigue", "mild", "neutral", "0"),
        image_row(
            "s01_no_face_normal_none_0001",
            "no_face",
            "unknown",
            "unknown",
            "0",
            face_visible="none",
            image_quality="unknown",
        ),
        image_row("s01_missing_normal_front_0001", "normal_focus", "none", "neutral", "0"),
    ]
    for row in rows[:-1]:
        touch(root, row["file_path"])
    write_csv(root / "labels/images_labels.csv", IMAGE_COLUMNS, rows)
    write_csv(
        root / "processed/face_roi/face_roi_manifest.csv",
        ROI_COLUMNS,
        [
            {
                "image_id": "s01_severe_sleepy_normal_front_0001",
                "file_path": "raw/images/s01_severe_sleepy_normal_front_0001.jpg",
                "roi_path": "processed/face_roi/s01_severe_sleepy_normal_front_0001.jpg",
                "status": "ok",
                "x1": "0",
                "y1": "0",
                "x2": "1",
                "y2": "1",
                "detector": "test",
                "note": "",
            },
            {
                "image_id": "s01_no_face_normal_none_0001",
                "file_path": "raw/images/s01_no_face_normal_none_0001.jpg",
                "roi_path": "",
                "status": "skipped",
                "x1": "",
                "y1": "",
                "x2": "",
                "y2": "",
                "detector": "",
                "note": "no_face_detected",
            },
        ],
    )


class EvaluateXiaoAnCarePolicyTest(unittest.TestCase):
    def test_fatigue_label_mapping(self):
        self.assertEqual(policy.fatigue_label_to_score_100("severe"), 85.0)
        self.assertEqual(policy.fatigue_label_to_score_100("none"), 10.0)
        self.assertIsNone(policy.fatigue_label_to_score_100("unknown"))

    def test_single_threshold_triggers_high_fatigue_only_above_threshold(self):
        high_sample = {"fatigue_score": 85.0, "emotion_tag": "neutral", "confidence": 0.6}
        low_sample = {"fatigue_score": 10.0, "emotion_tag": "neutral", "confidence": 0.6}

        high = policy.evaluate_sample_with_strategy(high_sample, "single_threshold", now_s=0)
        low = policy.evaluate_sample_with_strategy(low_sample, "single_threshold", now_s=10)

        self.assertTrue(high.high_level_care)
        self.assertFalse(low.high_level_care)

    def test_quality_gate_blocks_no_face_even_with_injected_high_signal(self):
        sample = {
            "scene": "no_face",
            "face_visible": "none",
            "image_quality": "unknown",
            "roi_status": "skipped",
            "fatigue_score": 85.0,
            "emotion_tag": "sad",
            "confidence": 0.9,
        }

        result = policy.evaluate_sample_with_strategy(sample, "quality_gate_plus_cooldown", now_s=0)

        self.assertFalse(result.high_level_care)
        self.assertTrue(result.suppressed_by_quality)
        self.assertEqual(result.action_level, 0)

    def test_quality_gate_allows_valid_severe_sleepy(self):
        sample = {
            "scene": "severe_sleepy",
            "face_visible": "yes",
            "image_quality": "good",
            "roi_status": "ok",
            "fatigue_score": 85.0,
            "emotion_tag": "neutral",
            "confidence": 0.6,
        }

        state = policy.PolicyState()
        result = policy.evaluate_sample_with_strategy(
            sample, "quality_gate_plus_cooldown", now_s=0, state=state
        )

        self.assertTrue(result.high_level_care)
        self.assertEqual(result.action_level, 3)

    def test_optional_mild_fatigue_is_not_counted_as_false_or_missed(self):
        result = policy.PolicyResult(
            strategy="single_threshold",
            image_id="mild",
            scene="mild_fatigue",
            expected_high_level_care="optional",
            status="evaluated",
            high_level_care=True,
            action_level=1,
            reason="expression_only",
        )

        metrics = policy.compute_metrics([result])

        self.assertEqual(metrics["optional_trigger_count"], 1)
        self.assertEqual(metrics["false_high_level_trigger_count"], 0)
        self.assertEqual(metrics["missed_high_level_trigger_count"], 0)

    def test_missing_file_is_skipped_and_not_counted_in_main_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            results, summary = policy.evaluate_dataset(root)

            single_results = [r for r in results if r.strategy == "single_threshold"]
            skipped = [r for r in single_results if r.status == "skipped_missing_file"]
            single_metrics = summary["strategies"]["single_threshold"]

            self.assertEqual(len(skipped), 1)
            self.assertEqual(single_metrics["skipped_missing_file_count"], 1)
            self.assertEqual(single_metrics["evaluated_count"], 4)

    def test_vlm_override_count_is_always_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            _results, summary = policy.evaluate_dataset(root)

            self.assertTrue(
                all(
                    metrics["vlm_override_count"] == 0
                    for metrics in summary["strategies"].values()
                )
            )

    def test_cli_entrypoint_runs_from_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset_root = tmp_path / "dataset"
            out_root = tmp_path / "report_assets"
            make_dataset(dataset_root)
            repo_root = Path(__file__).resolve().parents[2]

            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/evaluate_xiaoan_care_policy.py",
                    "--dataset-root",
                    str(dataset_root),
                    "--out",
                    str(out_root),
                ],
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((out_root / "logs/policy_eval_summary.json").exists())


if __name__ == "__main__":
    unittest.main()
