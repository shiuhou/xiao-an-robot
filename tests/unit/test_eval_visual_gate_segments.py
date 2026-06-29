"""Unit tests for visual gate segment evaluation."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools import eval_visual_gate_segments as evaluate


def _write_csv(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _row(
    timestamp_ms: int,
    *,
    should_trigger: bool = False,
    candidate_triggered: bool | None = None,
    reason: str = "normal",
    evidence_codes: list[str] | None = None,
    emotion_tag: str = "neutral",
    debug: dict | None = None,
    rules: dict | list | str | None = None,
) -> dict:
    row = {
        "timestamp_ms": timestamp_ms,
        "should_trigger": should_trigger,
        "reason": reason,
        "evidence_codes": evidence_codes or [],
        "emotion_tag": emotion_tag,
        "debug": debug or {},
        "rules": rules or {},
    }
    if candidate_triggered is not None:
        row.pop("should_trigger")
        row["candidate_triggered"] = candidate_triggered
    return row


class EvalVisualGateSegmentsTest(unittest.TestCase):
    def _run_eval(
        self,
        work: Path,
        annotation_text: str,
        trace_name: str | None,
        trace_rows: list[dict] | None,
        manifest_text: str | None = None,
    ) -> list[dict[str, str]]:
        annotations = work / "annotations" / "segment_labels.csv"
        traces = work / "traces"
        reports = work / "reports"
        _write_csv(annotations, annotation_text)
        traces.mkdir(parents=True, exist_ok=True)
        if trace_name is not None and trace_rows is not None:
            _write_jsonl(traces / trace_name, trace_rows)
        if manifest_text is not None:
            _write_csv(work / "annotations" / "video_manifest.csv", manifest_text)

        exit_code = evaluate.main([
            "--annotations", str(annotations),
            "--traces", str(traces),
            "--output-dir", str(reports),
        ])

        self.assertEqual(exit_code, 0)
        return _read_csv(reports / "gate_eval_segments.csv")

    def test_neutral_segment_with_zero_triggers_passes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rows = self._run_eval(
                Path(d),
                "video,segment_id,start_s,end_s,label,expected_gate,expected_reason,note\n"
                "U01_N01_T01.mp4,S01,0,10,neutral,false,,normal",
                "U01_N01_T01.jsonl",
                [_row(1000), _row(9000)],
            )
            self.assertEqual(rows[0]["total_frames"], "2")
            self.assertEqual(rows[0]["gate_count"], "0")
            self.assertEqual(rows[0]["result"], "pass")

    def test_neutral_segment_with_trigger_fails(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rows = self._run_eval(
                Path(d),
                "video,segment_id,start_s,end_s,label,expected_gate,expected_reason,note\n"
                "U01_N01_T01.mp4,S01,0,10,neutral,false,,normal",
                "U01_N01_T01.jsonl",
                [_row(5000, should_trigger=True, reason="force")],
            )
            self.assertEqual(rows[0]["gate_count"], "1")
            self.assertEqual(rows[0]["main_trigger_reason"], "force")
            self.assertEqual(rows[0]["result"], "fail")

    def test_negative_segment_with_negative_emotion_window_passes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rows = self._run_eval(
                Path(d),
                "video,segment_id,start_s,end_s,label,expected_gate,expected_reason,note\n"
                "U01_E01_T01.mp4,S02,5,10,negative,true,negative_emotion_window,negative",
                "U01_E01_T01.jsonl",
                [
                    _row(4999, should_trigger=True, reason="negative_emotion_window"),
                    _row(6000, should_trigger=True, reason="other", debug={"hit": "NEGATIVE_EMOTION_WINDOW"}, emotion_tag="sad"),
                ],
            )
            self.assertEqual(rows[0]["total_frames"], "1")
            self.assertEqual(rows[0]["negative_gate_count"], "1")
            self.assertEqual(rows[0]["negative_frame_count"], "1")
            self.assertEqual(rows[0]["result"], "pass")

    def test_fatigue_segment_with_high_fatigue_or_long_closure_passes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rows = self._run_eval(
                Path(d),
                "video,segment_id,start_s,end_s,label,expected_gate,expected_reason,note\n"
                "U01_Y01_T01.mp4,S02,5,10,fatigue,true,fatigue,fatigue",
                "U01_Y01_T01.jsonl",
                [
                    _row(6000, should_trigger=True, reason="high_fatigue"),
                    _row(7000, candidate_triggered=True, reason="normal", evidence_codes=["LONG_CLOSURE"]),
                ],
            )
            self.assertEqual(rows[0]["fatigue_gate_count"], "2")
            self.assertEqual(rows[0]["result"], "pass")

    def test_observe_segment_outputs_observe(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rows = self._run_eval(
                Path(d),
                "video,segment_id,start_s,end_s,label,expected_gate,expected_reason,note\n"
                "U01_C01_T01.mp4,S02,5,10,confused,observe,,observe",
                "U01_C01_T01.jsonl",
                [_row(6000, should_trigger=True, reason="force")],
            )
            self.assertEqual(rows[0]["result"], "observe")

    def test_trace_prefix_matches_video_stem(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rows = self._run_eval(
                Path(d),
                "video,segment_id,start_s,end_s,label,expected_gate,expected_reason,note\n"
                "U01_N01_T01.mp4,S01,0,10,neutral,false,,normal",
                "U01_N01_T01_20260621.jsonl",
                [_row(1000)],
            )
            self.assertEqual(rows[0]["total_frames"], "1")
            self.assertEqual(rows[0]["result"], "pass")


if __name__ == "__main__":
    unittest.main()
