import csv
import tempfile
import unittest
from pathlib import Path

from tools import evaluate_xiaoan_care_clips as clips


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


def clip_row(
    clip_id,
    clip_type,
    duration="4",
    start="1",
    end="3",
    care_needed="0",
    fatigue_label="none",
    face_visible="yes",
    image_quality="good",
):
    return {
        "clip_id": clip_id,
        "file_path": f"raw/clips/{clip_id}.mp4",
        "subject_id": "s01",
        "duration_sec": duration,
        "scene": clip_type,
        "light": "normal",
        "clip_type": clip_type,
        "face_visible": face_visible,
        "image_quality": image_quality,
        "closed_eye_event": "1" if "eyes_closed" in clip_type else "0",
        "yawn_event": "1" if clip_type == "yawn" else "0",
        "head_down_event": "1" if clip_type == "head_down_sleepy" else "0",
        "negative_affect_event": "0",
        "fatigue_label": fatigue_label,
        "care_needed": care_needed,
        "care_action": "",
        "start_time_sec": start,
        "end_time_sec": end,
        "note": "",
    }


def make_dataset(root):
    rows = [
        clip_row("normal_001", "normal_working", care_needed="0", fatigue_label="none"),
        clip_row("no_face_001", "no_face", care_needed="0", fatigue_label="unknown", face_visible="no", image_quality="no_face"),
        clip_row("yawn_001", "yawn", care_needed="1", fatigue_label="moderate"),
        clip_row("eyes_long_001", "eyes_closed_long", care_needed="1", fatigue_label="severe"),
        clip_row("eyes_short_001", "eyes_closed_short", care_needed="1", fatigue_label="mild"),
        clip_row("missing_001", "normal_working", care_needed="0", fatigue_label="none"),
        clip_row("conflict_001", "yawn", care_needed="0", fatigue_label="moderate"),
    ]
    for row in rows:
        if row["clip_id"] != "missing_001":
            touch(root, row["file_path"])
    write_csv(root / "labels/clips_labels.csv", CLIP_COLUMNS, rows)


class EvaluateXiaoAnCareClipsTest(unittest.TestCase):
    def test_each_clip_has_independent_cooldown_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            timeline, summaries, _summary = clips.evaluate_clip_dataset(root)
            yawn = next(item for item in summaries if item.clip_id == "yawn_001")
            eyes_long = next(item for item in summaries if item.clip_id == "eyes_long_001")

            self.assertEqual(yawn.first_trigger_time_s, 1.0)
            self.assertEqual(eyes_long.first_trigger_time_s, 1.0)
            self.assertEqual(yawn.high_level_trigger_count, 1)
            self.assertEqual(eyes_long.high_level_trigger_count, 1)
            self.assertTrue(any(row.clip_id == "yawn_001" for row in timeline))

    def test_normal_working_does_not_trigger_high_level_care(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            _timeline, summaries, _summary = clips.evaluate_clip_dataset(root)
            normal = next(item for item in summaries if item.clip_id == "normal_001")

            self.assertEqual(normal.result, "pass")
            self.assertEqual(normal.high_level_trigger_count, 0)

    def test_no_face_enters_quality_gate_and_does_not_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            timeline, summaries, _summary = clips.evaluate_clip_dataset(root)
            no_face = next(item for item in summaries if item.clip_id == "no_face_001")
            no_face_rows = [row for row in timeline if row.clip_id == "no_face_001"]

            self.assertEqual(no_face.result, "pass")
            self.assertEqual(no_face.high_level_trigger_count, 0)
            self.assertGreater(no_face.quality_suppressed_count, 0)
            self.assertTrue(all(row.state == "QUALITY_GATE" for row in no_face_rows))

    def test_yawn_and_eyes_closed_long_trigger_high_level_care(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            _timeline, summaries, _summary = clips.evaluate_clip_dataset(root)
            yawn = next(item for item in summaries if item.clip_id == "yawn_001")
            eyes_long = next(item for item in summaries if item.clip_id == "eyes_long_001")

            self.assertEqual(yawn.result, "pass")
            self.assertEqual(eyes_long.result, "pass")
            self.assertEqual(yawn.high_level_trigger_count, 1)
            self.assertEqual(eyes_long.high_level_trigger_count, 1)

    def test_eyes_closed_short_is_optional_expression_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            _timeline, summaries, _summary = clips.evaluate_clip_dataset(root)
            eyes_short = next(item for item in summaries if item.clip_id == "eyes_short_001")

            self.assertEqual(eyes_short.expected_high_level_care, "optional")
            self.assertEqual(eyes_short.high_level_trigger_count, 0)
            self.assertGreater(eyes_short.expression_only_count, 0)
            self.assertEqual(eyes_short.result, "pass")

    def test_after_first_trigger_same_clip_enters_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            timeline, summaries, _summary = clips.evaluate_clip_dataset(root)
            yawn = next(item for item in summaries if item.clip_id == "yawn_001")
            yawn_rows = [row for row in timeline if row.clip_id == "yawn_001"]

            self.assertGreater(yawn.cooldown_suppressed_count, 0)
            self.assertIn("COOLDOWN", {row.state for row in yawn_rows})

    def test_missing_clip_is_skipped_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            _timeline, summaries, summary = clips.evaluate_clip_dataset(root)
            missing = next(item for item in summaries if item.clip_id == "missing_001")

            self.assertEqual(missing.status, "skipped_missing_clip")
            self.assertEqual(summary["skipped_missing_clip_count"], 1)

    def test_timeline_csv_fields_are_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = Path(tmp) / "report_assets"
            make_dataset(root)

            clips.run_clip_eval(root, out)
            csv_path = out / "logs/clip_policy_timeline.csv"
            with csv_path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                columns = set(reader.fieldnames or [])

            expected = {
                "clip_id",
                "t_sec",
                "sample_kind",
                "clip_type",
                "scene",
                "fatigue_score_100",
                "emotion_tag",
                "confidence",
                "quality_valid",
                "state",
                "action_level",
                "high_level_care",
                "expression_only",
                "suppressed_by_quality",
                "suppressed_by_cooldown",
                "reason",
                "expected_high_level_care",
            }
            self.assertTrue(expected.issubset(columns))

    def test_label_conflict_warning_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)

            _timeline, summaries, summary = clips.evaluate_clip_dataset(root)
            conflict = next(item for item in summaries if item.clip_id == "conflict_001")

            self.assertTrue(conflict.label_conflict_warning)
            self.assertEqual(summary["label_conflict_warning_count"], 1)


if __name__ == "__main__":
    unittest.main()
