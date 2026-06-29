import csv
import tempfile
import unittest
from pathlib import Path

from tools import prepare_xiaoan_care_report_assets as assets


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

CLIP_COLUMNS = [
    "clip_id",
    "file_path",
    "subject_id",
    "duration_sec",
    "scene",
    "light",
    "clip_type",
    "face_visible",
    "image_quality",
    "closed_eye_event",
    "yawn_event",
    "head_down_event",
    "negative_affect_event",
    "fatigue_label",
    "care_needed",
    "care_action",
    "start_time_sec",
    "end_time_sec",
    "note",
]

VLM_COLUMNS = [
    "image_id",
    "file_path",
    "roi_path",
    "expected_fatigue",
    "expected_affect",
    "expected_care_needed",
    "expected_evidence",
    "expected_sentence",
    "split",
]

ROI_COLUMNS = [
    "image_id",
    "file_path",
    "roi_path",
    "status",
    "reason",
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


def make_dataset(root):
    touch(root, "raw/images/s01_normal_focus_normal_front_0001.jpg")
    touch(root, "raw/images/s01_yawn_normal_front_0001.jpg")
    touch(root, "raw/images/s01_bad_frame_normal_front_0001.jpg")
    touch(root, "raw/images/s01_normal_focus_normal_front_0002.jpg")
    touch(root, "processed/face_roi/s01_normal_focus_normal_front_0001.jpg")

    write_csv(
        root / "labels/images_labels.csv",
        IMAGE_COLUMNS,
        [
            {
                "image_id": "s01_normal_focus_normal_front_0001",
                "file_path": "raw/images/s01_normal_focus_normal_front_0001.jpg",
                "subject_id": "s01",
                "scene": "normal_focus",
                "light": "normal",
                "face_angle": "front",
                "face_visible": "1",
                "image_quality": "good",
                "eye_state": "open",
                "mouth_state": "closed",
                "head_pose": "front",
                "affect_label": "neutral",
                "fatigue_label": "none",
                "care_needed": "0",
                "care_action": "observe",
                "visible_evidence": "",
                "note": "",
            },
            {
                "image_id": "s01_yawn_normal_front_0001",
                "file_path": "raw/images/s01_yawn_normal_front_0001.jpg",
                "subject_id": "s01",
                "scene": "yawn",
                "light": "normal",
                "face_angle": "front",
                "face_visible": "1",
                "image_quality": "good",
                "eye_state": "open",
                "mouth_state": "yawn",
                "head_pose": "front",
                "affect_label": "neutral",
                "fatigue_label": "moderate",
                "care_needed": "1",
                "care_action": "fatigue_reminder",
                "visible_evidence": "yawn",
                "note": "",
            },
            {
                "image_id": "s01_bad_frame_normal_front_0001",
                "file_path": "raw/images/s01_bad_frame_normal_front_0001.jpg",
                "subject_id": "s01",
                "scene": "bad_frame",
                "light": "normal",
                "face_angle": "front",
                "face_visible": "0",
                "image_quality": "bad",
                "eye_state": "unknown",
                "mouth_state": "unknown",
                "head_pose": "unknown",
                "affect_label": "unknown",
                "fatigue_label": "unknown",
                "care_needed": "0",
                "care_action": "reject",
                "visible_evidence": "",
                "note": "",
            },
        ],
    )

    write_csv(
        root / "labels/clips_labels.csv",
        CLIP_COLUMNS,
        [
            {
                "clip_id": "clip_yawn_001",
                "file_path": "raw/clips/clip_yawn_001.mp4",
                "subject_id": "s01",
                "duration_sec": "5",
                "scene": "yawn",
                "light": "normal",
                "clip_type": "short",
                "face_visible": "1",
                "image_quality": "good",
                "closed_eye_event": "0",
                "yawn_event": "1",
                "head_down_event": "0",
                "negative_affect_event": "0",
                "fatigue_label": "moderate",
                "care_needed": "1",
                "care_action": "fatigue_reminder",
                "start_time_sec": "1",
                "end_time_sec": "5",
                "note": "",
            }
        ],
    )

    write_csv(
        root / "labels/vlm_eval_labels.csv",
        VLM_COLUMNS,
        [
            {
                "image_id": "s01_normal_focus_normal_front_0001",
                "file_path": "raw/images/s01_normal_focus_normal_front_0001.jpg",
                "roi_path": "processed/face_roi/s01_normal_focus_normal_front_0001.jpg",
                "expected_fatigue": "none",
                "expected_affect": "neutral",
                "expected_care_needed": "0",
                "expected_evidence": "focused",
                "expected_sentence": "The person looks focused.",
                "split": "test",
            }
        ],
    )

    write_csv(
        root / "processed/face_roi/face_roi_manifest.csv",
        ROI_COLUMNS,
        [
            {
                "image_id": "s01_normal_focus_normal_front_0001",
                "file_path": "raw/images/s01_normal_focus_normal_front_0001.jpg",
                "roi_path": "processed/face_roi/s01_normal_focus_normal_front_0001.jpg",
                "status": "ok",
                "reason": "",
            },
            {
                "image_id": "s01_bad_frame_normal_front_0001",
                "file_path": "raw/images/s01_bad_frame_normal_front_0001.jpg",
                "roi_path": "",
                "status": "skipped",
                "reason": "low_quality",
            },
        ],
    )


class PrepareXiaoAnCareReportAssetsTest(unittest.TestCase):
    def test_summary_counts_scene_care_needed_and_roi_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            summary = assets.build_dataset_summary(root)

            self.assertEqual(summary["totals"]["static_images"], 3)
            self.assertEqual(summary["totals"]["clips"], 1)
            self.assertEqual(summary["totals"]["vlm_eval"], 1)
            self.assertEqual(summary["totals"]["roi_manifest"], 2)
            self.assertEqual(summary["images"]["scene_distribution"]["normal_focus"], 1)
            self.assertEqual(summary["images"]["scene_distribution"]["yawn"], 1)
            self.assertEqual(summary["images"]["care_needed_distribution"], {"0": 2, "1": 1})
            self.assertEqual(summary["roi"]["overall_status"], {"ok": 1, "skipped": 1})
            self.assertEqual(summary["roi"]["status_by_scene"]["normal_focus"]["ok"], 1)
            self.assertEqual(summary["roi"]["status_by_scene"]["bad_frame"]["skipped"], 1)

    def test_missing_image_file_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            rows = assets.read_csv_rows(root / "labels/images_labels.csv")
            rows.append(
                {
                    **rows[0],
                    "image_id": "s01_missing_normal_front_0001",
                    "file_path": "raw/images/s01_missing_normal_front_0001.jpg",
                    "scene": "normal_focus",
                }
            )
            write_csv(root / "labels/images_labels.csv", IMAGE_COLUMNS, rows)

            issues = assets.find_dataset_issues(root)

            self.assertTrue(
                any(
                    issue["severity"] == "error"
                    and issue["code"] == "missing_file_path"
                    for issue in issues
                )
            )

    def test_skipped_roi_missing_path_is_warning_not_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            issues = assets.find_dataset_issues(root)
            skipped_issues = [
                issue for issue in issues if issue["code"] == "skipped_roi_missing_path"
            ]

            self.assertEqual(len(skipped_issues), 1)
            self.assertEqual(skipped_issues[0]["severity"], "warning")

    def test_focus_foucus_is_naming_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            touch(root, "raw/images/s01_normal_foucus_normal_front_0002.jpg")
            rows = assets.read_csv_rows(root / "labels/images_labels.csv")
            rows.append(
                {
                    **rows[0],
                    "image_id": "s01_normal_focus_normal_front_0002",
                    "file_path": "raw/images/s01_normal_foucus_normal_front_0002.jpg",
                    "scene": "normal_focus",
                }
            )
            write_csv(root / "labels/images_labels.csv", IMAGE_COLUMNS, rows)

            issues = assets.find_dataset_issues(root)

            self.assertTrue(
                any(
                    issue["severity"] == "warning"
                    and issue["code"] == "focus_foucus_inconsistency"
                    for issue in issues
                )
            )

    def test_no_face_vlm_missing_roi_is_not_applicable_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            touch(root, "raw/images/s01_no_face_normal_none_0001.jpg")
            image_rows = assets.read_csv_rows(root / "labels/images_labels.csv")
            image_rows.append(
                {
                    **image_rows[0],
                    "image_id": "s01_no_face_normal_none_0001",
                    "file_path": "raw/images/s01_no_face_normal_none_0001.jpg",
                    "scene": "no_face",
                    "face_visible": "no",
                    "image_quality": "no_face",
                    "affect_label": "unknown",
                    "fatigue_label": "unknown",
                    "care_needed": "0",
                }
            )
            write_csv(root / "labels/images_labels.csv", IMAGE_COLUMNS, image_rows)
            vlm_rows = assets.read_csv_rows(root / "labels/vlm_eval_labels.csv")
            vlm_rows.append(
                {
                    **vlm_rows[0],
                    "image_id": "s01_no_face_normal_none_0001",
                    "file_path": "raw/images/s01_no_face_normal_none_0001.jpg",
                    "roi_path": "N/A",
                    "expected_fatigue": "unknown",
                    "expected_affect": "unknown",
                    "expected_care_needed": "0",
                }
            )
            write_csv(root / "labels/vlm_eval_labels.csv", VLM_COLUMNS, vlm_rows)
            roi_rows = assets.read_csv_rows(root / "processed/face_roi/face_roi_manifest.csv")
            roi_rows.append(
                {
                    "image_id": "s01_no_face_normal_none_0001",
                    "file_path": "raw/images/s01_no_face_normal_none_0001.jpg",
                    "roi_path": "",
                    "status": "skipped",
                    "reason": "no_face_detected",
                }
            )
            write_csv(root / "processed/face_roi/face_roi_manifest.csv", ROI_COLUMNS, roi_rows)

            issues = assets.find_dataset_issues(root)

            self.assertTrue(
                any(
                    issue["severity"] == "info"
                    and issue["code"] == "roi_not_applicable"
                    and issue["file"] == "labels/vlm_eval_labels.csv"
                    for issue in issues
                )
            )
            self.assertFalse(
                any(
                    issue["severity"] == "error"
                    and issue["code"] == "missing_roi_path"
                    and issue["file"] == "labels/vlm_eval_labels.csv"
                    and issue["row"] == 3
                    for issue in issues
                )
            )


if __name__ == "__main__":
    unittest.main()
