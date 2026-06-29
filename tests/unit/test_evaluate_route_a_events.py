"""Unit tests for Route A event-level evaluation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import evaluate_route_a_events as evaluate


def _write_csv(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def _make_row(
    ts_ms: int,
    frame_id: int = 1,
    evidence_codes: list[str] | None = None,
    fatigue_level: str = "low",
    fatigue_score: float | None = 10.0,
    should_trigger: bool = False,
    gate_reason: str = "normal",
) -> dict:
    return {
        "frame": {"frame_id": frame_id, "timestamp_ms": ts_ms},
        "cv_sample": {
            "fatigue_score": fatigue_score,
            "fatigue_level": fatigue_level,
            "evidence_codes": evidence_codes or [],
            "observation_quality": 0.8,
            "presence_state": "present",
        },
        "gate_result": {
            "should_trigger": should_trigger,
            "reason": gate_reason,
        },
        "final_sample": {"fatigue_score": 99.0},
    }


DEFAULT_CONFIG = {
    "warmup_seconds": 5.0,
    "tolerance_seconds": 0.2,
    "false_trigger_episode_gap_seconds": 0.5,
}


class TestLoadAnnotations(unittest.TestCase):
    def test_reads_valid_csv(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ann.csv"
            _write_csv(p, (
                "clip_id,start_sec,end_sec,observable_event\n"
                "C01,0.0,5.0,normal\n"
                "C01,5.0,8.0,long_eye_closure\n"
            ))
            rows = evaluate.load_annotations(p)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["clip_id"], "C01")
            self.assertAlmostEqual(rows[1]["start_sec"], 5.0)

    def test_missing_column_raises(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.csv"
            _write_csv(p, "clip_id,start_sec,observable_event\nC01,0.0,normal\n")
            with self.assertRaisesRegex(ValueError, "end_sec"):
                evaluate.load_annotations(p)


class TestLoadTrace(unittest.TestCase):
    def test_corrupt_jsonl_reports_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "trace.jsonl"
            p.write_text('{"ok":true}\n{broken\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                evaluate.load_trace(p)


class TestGroupAnnotations(unittest.TestCase):
    def test_groups_by_clip_id(self) -> None:
        rows = [
            {"clip_id": "A", "start_sec": 0, "end_sec": 5, "observable_event": "normal"},
            {"clip_id": "B", "start_sec": 0, "end_sec": 3, "observable_event": "yawn"},
            {"clip_id": "A", "start_sec": 5, "end_sec": 8, "observable_event": "long_eye_closure"},
        ]
        groups = evaluate.group_annotations_by_clip(rows)
        self.assertEqual(len(groups["A"]), 2)
        self.assertEqual(len(groups["B"]), 1)


class TestWarmupExclusion(unittest.TestCase):
    def test_event_entirely_within_warmup_is_excluded(self) -> None:
        ann = {"clip_id": "C", "start_sec": 1.0, "end_sec": 3.0, "observable_event": "long_eye_closure"}
        trace = [_make_row(2000, evidence_codes=["LONG_CLOSURE"])]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertFalse(result["evaluable"])
        self.assertEqual(result["excluded_reason"], "entirely_within_warmup")

    def test_event_crossing_warmup_evaluates_effective_part(self) -> None:
        ann = {"clip_id": "C", "start_sec": 4.0, "end_sec": 6.0, "observable_event": "long_eye_closure"}
        trace = [_make_row(5100, evidence_codes=["LONG_CLOSURE"], fatigue_level="high")]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertTrue(result["evaluable"])
        self.assertTrue(result["partially_excluded_by_warmup"])
        self.assertAlmostEqual(result["effective_start_sec"], 5.0)
        self.assertTrue(result["cv_detected"])


class TestEyeClosureDetection(unittest.TestCase):
    def test_long_closure_evidence_hits(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 8.0, "observable_event": "long_eye_closure"}
        trace = [_make_row(6500, evidence_codes=["LONG_CLOSURE"])]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertTrue(result["cv_detected"])
        self.assertTrue(result["cv_evidence_hit"])

    def test_high_fatigue_level_hits(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 8.0, "observable_event": "long_eye_closure"}
        trace = [_make_row(7000, fatigue_level="high")]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertTrue(result["cv_detected"])
        self.assertTrue(result["cv_high_fatigue_hit"])

    def test_high_fatigue_gate_reason_matches(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 8.0, "observable_event": "long_eye_closure"}
        trace = [_make_row(7000, should_trigger=True, gate_reason="high_fatigue")]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertTrue(result["gate_reason_match"])


class TestYawnDetection(unittest.TestCase):
    def test_yawn_evidence_hits(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 8.0, "observable_event": "yawn"}
        trace = [_make_row(6500, evidence_codes=["YAWN"])]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertTrue(result["cv_detected"])

    def test_negative_emotion_window_not_yawn_match(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 8.0, "observable_event": "yawn"}
        trace = [_make_row(7000, should_trigger=True, gate_reason="negative_emotion_window")]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertTrue(result["gate_triggered_any"])
        self.assertFalse(result["gate_reason_match"])


class TestLatency(unittest.TestCase):
    def test_first_detection_latency_correct(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 9.0, "observable_event": "long_eye_closure"}
        trace = [
            _make_row(7000, evidence_codes=["LONG_CLOSURE"]),
            _make_row(8000, evidence_codes=["LONG_CLOSURE"]),
        ]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertAlmostEqual(result["cv_first_detection_sec"], 7.0)
        self.assertAlmostEqual(result["cv_latency_sec"], 1.0)

    def test_preexisting_trigger_marked(self) -> None:
        ann = {"clip_id": "C", "start_sec": 7.0, "end_sec": 9.0, "observable_event": "long_eye_closure"}
        trace = [
            _make_row(6900, should_trigger=True, gate_reason="high_fatigue"),
            _make_row(7500, should_trigger=True, gate_reason="high_fatigue",
                      evidence_codes=["LONG_CLOSURE"]),
        ]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertTrue(result["preexisting_gate_trigger"])
        self.assertTrue(result["detection_ambiguous_due_to_preexisting_trigger"])


class TestNormalInterval(unittest.TestCase):
    def test_false_trigger_frame_count(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 10.0, "observable_event": "normal"}
        trace = [
            _make_row(6000),
            _make_row(7000, should_trigger=True, gate_reason="negative_emotion_window"),
            _make_row(8000, should_trigger=True, gate_reason="negative_emotion_window"),
            _make_row(9000),
        ]
        result = evaluate.evaluate_normal_interval(ann, trace, DEFAULT_CONFIG)
        self.assertEqual(result["false_trigger_frame_count"], 2)
        self.assertEqual(result["frame_count"], 4)

    def test_episodes_merged_within_gap(self) -> None:
        rows = [(6.0, "r"), (6.3, "r"), (6.5, "r")]
        episodes = evaluate.merge_false_trigger_episodes(rows, 0.5)
        self.assertEqual(len(episodes), 1)

    def test_episodes_split_beyond_gap(self) -> None:
        rows = [(6.0, "r"), (6.3, "r"), (7.0, "r")]
        episodes = evaluate.merge_false_trigger_episodes(rows, 0.5)
        self.assertEqual(len(episodes), 2)

    def test_unexpected_evidence_counted(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 10.0, "observable_event": "normal"}
        trace = [
            _make_row(7000, evidence_codes=["PERCLOS_MID"]),
            _make_row(8000, evidence_codes=["LONG_CLOSURE", "PERCLOS_HIGH"]),
        ]
        result = evaluate.evaluate_normal_interval(ann, trace, DEFAULT_CONFIG)
        self.assertEqual(result["unexpected_evidence_code_counts"]["PERCLOS_MID"], 1)
        self.assertEqual(result["unexpected_evidence_code_counts"]["LONG_CLOSURE"], 1)
        self.assertEqual(result["unexpected_evidence_code_counts"]["PERCLOS_HIGH"], 1)


class TestAggregate(unittest.TestCase):
    def test_recall_correct(self) -> None:
        clips = {
            "A": {
                "events": [
                    {"event_type": "long_eye_closure", "evaluable": True,
                     "cv_detected": True, "gate_reason_match": True,
                     "cv_latency_sec": 1.0, "gate_latency_sec": 0.5},
                    {"event_type": "long_eye_closure", "evaluable": True,
                     "cv_detected": False, "gate_reason_match": False,
                     "cv_latency_sec": None, "gate_latency_sec": None},
                ],
                "normal_intervals": [
                    {"frame_count": 100, "false_trigger_frame_count": 10,
                     "false_trigger_episode_count": 2},
                ],
            },
        }
        agg = evaluate.aggregate_results(clips)
        self.assertEqual(agg["long_eye_closure"]["evaluable"], 2)
        self.assertAlmostEqual(agg["long_eye_closure"]["cv_event_recall"], 0.5)
        self.assertAlmostEqual(agg["long_eye_closure"]["gate_event_recall"], 0.5)
        self.assertEqual(agg["normal"]["false_trigger_frame_count"], 10)

    def test_recall_null_when_zero_evaluable(self) -> None:
        clips = {
            "A": {
                "events": [
                    {"event_type": "yawn", "evaluable": False,
                     "excluded_reason": "entirely_within_warmup"},
                ],
                "normal_intervals": [],
            },
        }
        agg = evaluate.aggregate_results(clips)
        self.assertIsNone(agg["yawn"]["cv_event_recall"])
        self.assertIsNone(agg["yawn"]["gate_event_recall"])


class TestDoesNotUseFinalSample(unittest.TestCase):
    def test_final_sample_fatigue_score_not_read(self) -> None:
        ann = {"clip_id": "C", "start_sec": 6.0, "end_sec": 8.0, "observable_event": "long_eye_closure"}
        trace = [{
            "frame": {"frame_id": 1, "timestamp_ms": 7000},
            "cv_sample": {
                "fatigue_score": 10.0,
                "fatigue_level": "low",
                "evidence_codes": [],
                "observation_quality": 0.8,
                "presence_state": "present",
            },
            "gate_result": {"should_trigger": False, "reason": "normal"},
            "final_sample": {"fatigue_score": 100.0, "fatigue_level": "high"},
        }]
        result = evaluate.evaluate_event(ann, trace, DEFAULT_CONFIG)
        self.assertFalse(result["cv_detected"])
        self.assertFalse(result["cv_high_fatigue_hit"])


class TestMissingClipTrace(unittest.TestCase):
    def test_missing_trace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            csv_path = work / "ann.csv"
            _write_csv(csv_path, (
                "clip_id,start_sec,end_sec,observable_event\n"
                "MISSING_CLIP,0.0,5.0,normal\n"
            ))
            traces_dir = work / "traces"
            traces_dir.mkdir()
            exit_code = evaluate.main([
                "--annotations", str(csv_path),
                "--traces-dir", str(traces_dir),
                "--output", str(work / "out.json"),
            ])
            self.assertNotEqual(exit_code, 0)


class TestCLIOutputDir(unittest.TestCase):
    def test_creates_output_directory_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            csv_path = work / "ann.csv"
            _write_csv(csv_path, (
                "clip_id,start_sec,end_sec,observable_event\n"
                "C01,6.0,8.0,normal\n"
            ))
            traces_dir = work / "traces"
            traces_dir.mkdir()
            _write_jsonl(traces_dir / "C01.jsonl", [_make_row(7000)])
            output = work / "nested" / "deep" / "report.json"

            exit_code = evaluate.main([
                "--annotations", str(csv_path),
                "--traces-dir", str(traces_dir),
                "--output", str(output),
            ])
            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], "route_a_event_eval_v0.1")


if __name__ == "__main__":
    unittest.main()
