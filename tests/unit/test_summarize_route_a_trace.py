"""Unit tests for the read-only Route A JSONL baseline summarizer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import summarize_route_a_trace as summarize


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sample_rows() -> list[dict]:
    return [
        {
            "frame": {"frame_id": 1, "timestamp_ms": 100},
            "obs": {"has_landmarks": True},
            "cv_sample": {
                "fatigue_score": 10.0,
                "fatigue_level": "low",
                "observation_quality": 0.9,
                "presence_state": "present",
                "evidence_codes": ["BASELINE"],
            },
            "gate_result": {"should_trigger": False, "reason": "normal"},
            "gate_state": {
                "vlm_enabled": True,
                "vlm_executed": False,
                "vlm_suppressed_by_cooldown": False,
                "vlm_elapsed_seconds": None,
            },
            "vlm_result": None,
            "final_sample": {"fatigue_score": 99.0},
        },
        {
            "frame": {"frame_id": 2, "timestamp_ms": 250},
            "obs": {"has_landmarks": False},
            "cv_sample": {
                "fatigue_score": None,
                "fatigue_level": "medium",
                "observation_quality": 0.4,
                "presence_state": None,
                "evidence_codes": ["PERCLOS_HIGH", "BASELINE"],
            },
            "gate_result": {"should_trigger": True, "reason": "high_fatigue"},
            "gate_state": {
                "vlm_enabled": True,
                "vlm_executed": False,
                "vlm_suppressed_by_cooldown": True,
                "vlm_elapsed_seconds": None,
            },
            "vlm_result": None,
            "final_sample": {"fatigue_score": 88.0},
        },
        {
            "frame": {"frame_id": 3, "timestamp_ms": 200},
            "obs": {"has_landmarks": True},
            "cv_sample": {
                "fatigue_score": 30.0,
                "fatigue_level": "high",
                "observation_quality": 0.2,
                "presence_state": "uncertain",
                "evidence_codes": ["LONG_EYE_CLOSURE"],
            },
            "gate_result": {"should_trigger": True, "reason": "negative_emotion"},
            "gate_state": {
                "vlm_enabled": True,
                "vlm_executed": True,
                "vlm_suppressed_by_cooldown": False,
                "vlm_elapsed_seconds": 1.5,
            },
            "vlm_result": {"emotion_tag": "tired"},
            "final_sample": {"fatigue_score": 77.0},
        },
    ]


class SummarizeRouteATraceTest(unittest.TestCase):
    def test_load_trace_rows_reads_multiline_jsonl(self) -> None:
        trace_path = Path(self._testMethodName + ".jsonl")
        self.addCleanup(lambda: trace_path.unlink(missing_ok=True))
        rows = _sample_rows()[:2]
        _write_jsonl(trace_path, rows)

        loaded = summarize.load_trace_rows(trace_path)

        self.assertEqual(loaded, rows)

    def test_summarize_frame_timeline_and_nonmonotonic_timestamps(self) -> None:
        report = summarize.summarize_trace(_sample_rows(), Path("trace.jsonl"))

        self.assertEqual(report["frame_summary"]["total_rows"], 3)
        self.assertEqual(report["frame_summary"]["first_frame_id"], 1)
        self.assertEqual(report["frame_summary"]["last_frame_id"], 3)
        self.assertEqual(report["frame_summary"]["first_timestamp_ms"], 100)
        self.assertEqual(report["frame_summary"]["last_timestamp_ms"], 200)
        self.assertEqual(report["frame_summary"]["duration_ms"], 100)
        self.assertFalse(report["frame_summary"]["timestamps_monotonic"])

    def test_duration_is_null_when_fewer_than_two_timestamps_exist(self) -> None:
        report = summarize.summarize_trace(
            [{"frame": {"frame_id": 1, "timestamp_ms": 100}}],
            Path("trace.jsonl"),
        )

        self.assertEqual(report["frame_summary"]["first_timestamp_ms"], 100)
        self.assertEqual(report["frame_summary"]["last_timestamp_ms"], 100)
        self.assertIsNone(report["frame_summary"]["duration_ms"])

    def test_face_presence_quality_fatigue_gate_and_vlm_metrics(self) -> None:
        report = summarize.summarize_trace(_sample_rows(), Path("trace.jsonl"), quality_threshold=0.5)

        self.assertEqual(report["face_summary"]["valid_face_frames"], 2)
        self.assertAlmostEqual(report["face_summary"]["valid_face_ratio"], 2 / 3)
        self.assertEqual(
            report["face_summary"]["presence_state_counts"],
            {"present": 1, "missing": 1, "uncertain": 1},
        )
        self.assertEqual(report["quality_summary"]["numeric_sample_count"], 3)
        self.assertAlmostEqual(report["quality_summary"]["mean"], 0.5)
        self.assertEqual(report["quality_summary"]["minimum"], 0.2)
        self.assertEqual(report["quality_summary"]["maximum"], 0.9)
        self.assertEqual(report["quality_summary"]["low_quality_frames"], 2)
        self.assertAlmostEqual(report["quality_summary"]["low_quality_ratio"], 2 / 3)

        self.assertEqual(report["fatigue_summary"]["numeric_sample_count"], 2)
        self.assertAlmostEqual(report["fatigue_summary"]["mean"], 20.0)
        self.assertEqual(report["fatigue_summary"]["minimum"], 10.0)
        self.assertEqual(report["fatigue_summary"]["maximum"], 30.0)
        self.assertEqual(
            report["fatigue_summary"]["fatigue_level_counts"],
            {"low": 1, "medium": 1, "high": 1},
        )
        self.assertEqual(
            report["fatigue_summary"]["evidence_code_counts"],
            {"BASELINE": 2, "PERCLOS_HIGH": 1, "LONG_EYE_CLOSURE": 1},
        )

        self.assertEqual(report["gate_summary"]["trigger_frame_count"], 2)
        self.assertAlmostEqual(report["gate_summary"]["trigger_frame_ratio"], 2 / 3)
        self.assertEqual(
            report["gate_summary"]["reason_counts"],
            {"normal": 1, "high_fatigue": 1, "negative_emotion": 1},
        )
        self.assertEqual(
            report["gate_summary"]["trigger_frames"],
            [
                {"frame_id": 2, "timestamp_ms": 250, "reason": "high_fatigue"},
                {"frame_id": 3, "timestamp_ms": 200, "reason": "negative_emotion"},
            ],
        )

        self.assertEqual(report["vlm_summary"]["enabled_frame_count"], 3)
        self.assertEqual(report["vlm_summary"]["executed_frame_count"], 1)
        self.assertEqual(report["vlm_summary"]["result_frame_count"], 1)
        self.assertEqual(report["vlm_summary"]["suppressed_by_cooldown_count"], 1)
        self.assertEqual(report["vlm_summary"]["missing_result_after_execution_count"], 0)
        self.assertEqual(report["vlm_summary"]["latency_sample_count"], 1)
        self.assertEqual(report["vlm_summary"]["latency_seconds_mean"], 1.5)
        self.assertEqual(report["vlm_summary"]["latency_seconds_minimum"], 1.5)
        self.assertEqual(report["vlm_summary"]["latency_seconds_maximum"], 1.5)

    def test_final_sample_fatigue_score_is_not_used_for_cv_fatigue(self) -> None:
        rows = [
            {
                "frame": {"frame_id": 1, "timestamp_ms": 0},
                "obs": {"has_landmarks": True},
                "cv_sample": {"fatigue_score": 4.0},
                "gate_result": {"should_trigger": False, "reason": "normal"},
                "gate_state": {},
                "final_sample": {"fatigue_score": 100.0},
            }
        ]

        report = summarize.summarize_trace(rows, Path("trace.jsonl"))

        self.assertEqual(report["fatigue_summary"]["mean"], 4.0)
        self.assertEqual(report["fatigue_summary"]["maximum"], 4.0)

    def test_missing_optional_sections_are_counted_without_crashing(self) -> None:
        report = summarize.summarize_trace([{"frame": {"frame_id": 1, "timestamp_ms": 10}}], Path("trace.jsonl"))

        self.assertEqual(report["missing_data"]["rows_missing_frame"], 0)
        self.assertEqual(report["missing_data"]["rows_missing_obs"], 1)
        self.assertEqual(report["missing_data"]["rows_missing_cv_sample"], 1)
        self.assertEqual(report["missing_data"]["rows_missing_gate_result"], 1)
        self.assertEqual(report["missing_data"]["rows_missing_gate_state"], 1)
        self.assertEqual(report["face_summary"]["valid_face_frames"], 0)

    def test_empty_file_fails(self) -> None:
        trace_path = Path(self._testMethodName + ".jsonl")
        self.addCleanup(lambda: trace_path.unlink(missing_ok=True))
        trace_path.write_text("", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "empty"):
            summarize.load_trace_rows(trace_path)

    def test_corrupt_json_line_fails_with_line_number(self) -> None:
        trace_path = Path(self._testMethodName + ".jsonl")
        self.addCleanup(lambda: trace_path.unlink(missing_ok=True))
        trace_path.write_text('{"ok": true}\n{broken\n', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "line 2"):
            summarize.load_trace_rows(trace_path)

    def test_main_writes_report_and_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            trace_path = work_dir / "trace.jsonl"
            output_path = work_dir / "nested" / "report.json"
            _write_jsonl(trace_path, _sample_rows()[:1])

            exit_code = summarize.main(["--input", str(trace_path), "--output", str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], "route_a_baseline_v0.1")
            self.assertEqual(report["frame_summary"]["total_rows"], 1)

    def test_format_terminal_summary_uses_gate_trigger_frames_label(self) -> None:
        report = summarize.summarize_trace(_sample_rows(), Path("trace.jsonl"))

        text = summarize.format_terminal_summary(report)

        self.assertIn("Route A baseline summary", text)
        self.assertIn("Gate trigger frames: 2/3 (66.67%)", text)
        self.assertNotIn("events", text.lower())


if __name__ == "__main__":
    unittest.main()
