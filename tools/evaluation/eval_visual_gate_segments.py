#!/usr/bin/env python
"""Evaluate visual Gate traces over labeled video segments."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any


SEGMENT_COLUMNS = [
    "video",
    "segment_id",
    "label",
    "start_s",
    "end_s",
    "expected_gate",
    "expected_reason",
    "total_frames",
    "gate_count",
    "gate_rate",
    "negative_gate_count",
    "fatigue_gate_count",
    "negative_frame_count",
    "negative_frame_rate",
    "first_trigger_s",
    "main_trigger_reason",
    "result",
]

SUMMARY_COLUMNS = [
    "video",
    "scenario",
    "total_segments",
    "pass_segments",
    "fail_segments",
    "observe_segments",
    "total_gate_count",
    "negative_gate_count",
    "fatigue_gate_count",
    "conclusion",
]

REQUIRED_ANNOTATION_COLUMNS = {
    "video",
    "segment_id",
    "start_s",
    "end_s",
    "label",
    "expected_gate",
    "expected_reason",
    "note",
}
NEGATIVE_EMOTIONS = {"negative", "sad", "angry", "fear", "disgust"}
FATIGUE_EVIDENCE_CODES = {"perclos_high", "long_closure", "yawn"}


def _as_lower_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    return json.dumps(value, ensure_ascii=False, sort_keys=True).lower()


def _section(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    return value if isinstance(value, dict) else {}


def _first_value(row: dict[str, Any], keys: list[str], sections: list[str]) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    for section_name in sections:
        section = _section(row, section_name)
        for key in keys:
            if key in section:
                return section[key]
    return None


def timestamp_s(row: dict[str, Any]) -> float | None:
    value = _first_value(
        row,
        ["timestamp_ms"],
        ["frame", "cv_sample", "gate_result"],
    )
    if value is not None:
        return float(value) / 1000.0
    value = _first_value(
        row,
        ["timestamp_s"],
        ["frame", "cv_sample", "gate_result"],
    )
    if value is not None:
        return float(value)
    return None


def gate_triggered(row: dict[str, Any]) -> bool:
    value = _first_value(
        row,
        ["should_trigger", "candidate_triggered", "gate_triggered"],
        ["gate_result", "gate_state", "cv_sample"],
    )
    return bool(value)


def gate_reason(row: dict[str, Any]) -> str:
    value = _first_value(
        row,
        ["reason", "trigger_reason", "gate_reason"],
        ["gate_result", "gate_state", "cv_sample"],
    )
    text = str(value) if value not in (None, "") else "missing"
    return text


def emotion_value(row: dict[str, Any]) -> str:
    value = _first_value(
        row,
        ["emotion_tag", "cv_emotion_raw", "emotion_raw", "emotion_label"],
        ["cv_sample", "final_sample", "obs"],
    )
    return _as_lower_text(value).strip()


def evidence_codes(row: dict[str, Any]) -> list[str]:
    value = _first_value(
        row,
        ["evidence_codes"],
        ["cv_sample", "final_sample", "gate_result", "gate_state"],
    )
    if isinstance(value, list):
        return [_as_lower_text(v) for v in value]
    if isinstance(value, str):
        return [_as_lower_text(value)]
    return []


def contains_negative_window(row: dict[str, Any], reason: str) -> bool:
    if reason.lower() == "negative_emotion_window":
        return True
    haystack = " ".join([
        _as_lower_text(row.get("evidence")),
        _as_lower_text(row.get("debug")),
        _as_lower_text(row.get("rules")),
        _as_lower_text(_section(row, "gate_result").get("evidence")),
        _as_lower_text(_section(row, "gate_result").get("debug")),
        _as_lower_text(_section(row, "gate_result").get("rules")),
    ])
    return "negative_emotion_window" in haystack


def contains_fatigue(row: dict[str, Any], reason: str) -> bool:
    reason_text = reason.lower()
    if "high_fatigue" in reason_text or "fatigue" in reason_text:
        return True
    return any(code in FATIGUE_EVIDENCE_CODES for code in evidence_codes(row))


def load_annotations(path: str | Path) -> list[dict[str, Any]]:
    ann_path = Path(path)
    with ann_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"annotations file is empty: {ann_path}")
        missing = REQUIRED_ANNOTATION_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"annotations CSV missing columns: {sorted(missing)}")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            rows.append({
                "video": row["video"],
                "segment_id": row["segment_id"],
                "start_s": float(row["start_s"]),
                "end_s": float(row["end_s"]),
                "label": row["label"],
                "expected_gate": row["expected_gate"].strip().lower(),
                "expected_reason": row["expected_reason"].strip().lower(),
                "note": row["note"],
                "_line": line_number,
            })
    return rows


def load_manifest(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    manifest_path = Path(path)
    if not manifest_path.exists():
        return {}
    scenarios: dict[str, str] = {}
    with manifest_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return {}
        if "video" not in reader.fieldnames or "scenario" not in reader.fieldnames:
            return {}
        for row in reader:
            scenarios[row["video"]] = row.get("scenario", "")
    return scenarios


def load_trace(path: str | Path) -> list[dict[str, Any]]:
    trace_path = Path(path)
    rows: list[dict[str, Any]] = []
    with trace_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSONL parse error in {trace_path} line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL parse error in {trace_path} line {line_number}: expected object"
                )
            rows.append(value)
    return rows


def find_trace_for_video(video: str, traces_dir: str | Path) -> Path | None:
    stem = Path(video).stem
    matches = list(Path(traces_dir).glob(f"{stem}*.jsonl"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def is_last_segment(segment: dict[str, Any], segments_for_video: list[dict[str, Any]]) -> bool:
    max_end = max(float(seg["end_s"]) for seg in segments_for_video)
    return float(segment["end_s"]) == max_end


def frames_for_segment(
    trace_rows: list[dict[str, Any]],
    segment: dict[str, Any],
    include_end: bool,
) -> list[tuple[float, dict[str, Any]]]:
    start = float(segment["start_s"])
    end = float(segment["end_s"])
    frames = []
    for row in trace_rows:
        ts = timestamp_s(row)
        if ts is None:
            continue
        if start <= ts < end or (include_end and ts == end):
            frames.append((ts, row))
    return frames


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0000"
    return f"{numerator / denominator:.4f}"


def _format_second(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def evaluate_segment(
    segment: dict[str, Any],
    frames: list[tuple[float, dict[str, Any]]],
) -> dict[str, Any]:
    gate_count = 0
    negative_gate_count = 0
    fatigue_gate_count = 0
    negative_frame_count = 0
    first_trigger_s: float | None = None
    trigger_reason_counts: Counter[str] = Counter()

    for ts, row in frames:
        reason = gate_reason(row)
        triggered = gate_triggered(row)
        is_negative = contains_negative_window(row, reason)
        is_fatigue = contains_fatigue(row, reason)
        if emotion_value(row) in NEGATIVE_EMOTIONS:
            negative_frame_count += 1
        if triggered:
            gate_count += 1
            trigger_reason_counts[reason] += 1
            if first_trigger_s is None:
                first_trigger_s = ts
            if is_negative:
                negative_gate_count += 1
            if is_fatigue:
                fatigue_gate_count += 1

    expected_gate = segment["expected_gate"]
    expected_reason = segment["expected_reason"]
    if expected_gate == "observe":
        result = "observe"
    elif expected_gate == "false":
        result = "pass" if gate_count == 0 else "fail"
    elif expected_gate == "true" and expected_reason == "negative_emotion_window":
        result = "pass" if negative_gate_count > 0 else "fail"
    elif expected_gate == "true" and expected_reason == "fatigue":
        result = "pass" if fatigue_gate_count > 0 else "fail"
    else:
        result = "fail"

    main_reason = "none"
    if trigger_reason_counts:
        main_reason = trigger_reason_counts.most_common(1)[0][0]

    total_frames = len(frames)
    return {
        "video": segment["video"],
        "segment_id": segment["segment_id"],
        "label": segment["label"],
        "start_s": _format_second(float(segment["start_s"])),
        "end_s": _format_second(float(segment["end_s"])),
        "expected_gate": expected_gate,
        "expected_reason": expected_reason,
        "total_frames": total_frames,
        "gate_count": gate_count,
        "gate_rate": _rate(gate_count, total_frames),
        "negative_gate_count": negative_gate_count,
        "fatigue_gate_count": fatigue_gate_count,
        "negative_frame_count": negative_frame_count,
        "negative_frame_rate": _rate(negative_frame_count, total_frames),
        "first_trigger_s": _format_second(first_trigger_s),
        "main_trigger_reason": main_reason,
        "result": result,
    }


def group_segments_by_video(
    annotations: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in annotations:
        grouped.setdefault(row["video"], []).append(row)
    return grouped


def evaluate_all(
    annotations: list[dict[str, Any]],
    traces_dir: str | Path,
) -> list[dict[str, Any]]:
    grouped = group_segments_by_video(annotations)
    results: list[dict[str, Any]] = []
    for video, segments in grouped.items():
        trace_path = find_trace_for_video(video, traces_dir)
        if trace_path is None:
            print(f"warning: missing trace for video {video}", file=sys.stderr)
            trace_rows: list[dict[str, Any]] = []
        else:
            trace_rows = load_trace(trace_path)

        for segment in segments:
            include_end = is_last_segment(segment, segments)
            frames = frames_for_segment(trace_rows, segment, include_end)
            results.append(evaluate_segment(segment, frames))
    return results


def summarize_segments(
    segment_rows: list[dict[str, Any]],
    scenarios: dict[str, str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in segment_rows:
        grouped.setdefault(row["video"], []).append(row)

    summaries: list[dict[str, Any]] = []
    for video, rows in grouped.items():
        pass_count = sum(1 for row in rows if row["result"] == "pass")
        fail_count = sum(1 for row in rows if row["result"] == "fail")
        observe_count = sum(1 for row in rows if row["result"] == "observe")
        if fail_count:
            conclusion = "fail"
        elif observe_count and not pass_count:
            conclusion = "observe"
        elif observe_count:
            conclusion = "pass_with_observe"
        else:
            conclusion = "pass"
        summaries.append({
            "video": video,
            "scenario": scenarios.get(video, ""),
            "total_segments": len(rows),
            "pass_segments": pass_count,
            "fail_segments": fail_count,
            "observe_segments": observe_count,
            "total_gate_count": sum(int(row["gate_count"]) for row in rows),
            "negative_gate_count": sum(int(row["negative_gate_count"]) for row in rows),
            "fatigue_gate_count": sum(int(row["fatigue_gate_count"]) for row in rows),
            "conclusion": conclusion,
        })
    return summaries


def write_csv(path: str | Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate visual Gate trace JSONL files by labeled segments.",
    )
    parser.add_argument("--annotations", required=True, help="Path to segment_labels.csv.")
    parser.add_argument("--traces", required=True, help="Directory containing JSONL traces.")
    parser.add_argument("--output-dir", required=True, help="Directory for report CSV files.")
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional path to video_manifest.csv. Defaults to annotations sibling.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    annotations_path = Path(args.annotations)
    manifest_path = Path(args.manifest) if args.manifest else annotations_path.parent / "video_manifest.csv"
    output_dir = Path(args.output_dir)

    try:
        annotations = load_annotations(annotations_path)
        scenarios = load_manifest(manifest_path)
        segment_rows = evaluate_all(annotations, args.traces)
        summary_rows = summarize_segments(segment_rows, scenarios)
        write_csv(output_dir / "gate_eval_segments.csv", segment_rows, SEGMENT_COLUMNS)
        write_csv(output_dir / "gate_eval_summary.csv", summary_rows, SUMMARY_COLUMNS)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {output_dir / 'gate_eval_segments.csv'}")
    print(f"Wrote {output_dir / 'gate_eval_summary.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
