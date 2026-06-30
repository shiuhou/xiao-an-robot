#!/usr/bin/env python
"""Summarize a single Route A JSONL trace into read-only baseline metrics."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


SCHEMA_VERSION = "route_a_baseline_v0.1"


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _numeric_values(values: list[Any]) -> list[float]:
    return [float(value) for value in values if _is_numeric(value)]


def _numeric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "numeric_sample_count": 0,
            "mean": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "numeric_sample_count": len(values),
        "mean": statistics.fmean(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _section(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    return value if isinstance(value, dict) else {}


def _count_key(counter: Counter[str], value: Any) -> None:
    counter[str(value) if value is not None else "missing"] += 1


def _is_present_section(row: dict[str, Any], key: str) -> bool:
    return isinstance(row.get(key), dict)


def _has_vlm_result(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def load_trace_rows(path: str | Path) -> list[dict[str, Any]]:
    trace_path = Path(path)
    rows: list[dict[str, Any]] = []
    try:
        with trace_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"JSONL parse error on line {line_number}: {exc.msg}") from exc
                if not isinstance(parsed, dict):
                    raise ValueError(f"JSONL parse error on line {line_number}: expected object")
                rows.append(parsed)
    except FileNotFoundError as exc:
        raise ValueError(f"input file does not exist: {trace_path}") from exc

    if not rows:
        raise ValueError(f"input file is empty: {trace_path}")
    return rows


def summarize_trace(
    rows: list[dict[str, Any]],
    input_path: str | Path,
    quality_threshold: float = 0.5,
) -> dict[str, Any]:
    trace_path = Path(input_path)
    total_rows = len(rows)
    frames = [_section(row, "frame") for row in rows]

    first_frame = frames[0] if frames else {}
    last_frame = frames[-1] if frames else {}
    first_timestamp = first_frame.get("timestamp_ms")
    last_timestamp = last_frame.get("timestamp_ms")
    timestamp_values = [frame.get("timestamp_ms") for frame in frames if _is_numeric(frame.get("timestamp_ms"))]
    duration_ms = (
        last_timestamp - first_timestamp
        if len(timestamp_values) >= 2 and _is_numeric(first_timestamp) and _is_numeric(last_timestamp)
        else None
    )
    timestamps_monotonic = all(
        right >= left for left, right in zip(timestamp_values, timestamp_values[1:])
    )

    valid_face_frames = 0
    presence_counts: Counter[str] = Counter()
    quality_values: list[Any] = []
    fatigue_values: list[Any] = []
    fatigue_level_counts: Counter[str] = Counter()
    evidence_code_counts: Counter[str] = Counter()
    trigger_frames: list[dict[str, Any]] = []
    gate_reason_counts: Counter[str] = Counter()
    vlm_enabled_count = 0
    vlm_executed_count = 0
    vlm_result_count = 0
    cooldown_count = 0
    missing_result_after_execution_count = 0
    latency_values: list[Any] = []

    missing_data = {
        "rows_missing_frame": 0,
        "rows_missing_obs": 0,
        "rows_missing_cv_sample": 0,
        "rows_missing_gate_result": 0,
        "rows_missing_gate_state": 0,
    }

    for row in rows:
        if not _is_present_section(row, "frame"):
            missing_data["rows_missing_frame"] += 1
        if not _is_present_section(row, "obs"):
            missing_data["rows_missing_obs"] += 1
        if not _is_present_section(row, "cv_sample"):
            missing_data["rows_missing_cv_sample"] += 1
        if not _is_present_section(row, "gate_result"):
            missing_data["rows_missing_gate_result"] += 1
        if not _is_present_section(row, "gate_state"):
            missing_data["rows_missing_gate_state"] += 1

        frame = _section(row, "frame")
        obs = _section(row, "obs")
        cv_sample = _section(row, "cv_sample")
        gate_result = _section(row, "gate_result")
        gate_state = _section(row, "gate_state")

        if obs.get("has_landmarks") is True:
            valid_face_frames += 1

        _count_key(presence_counts, cv_sample.get("presence_state"))
        quality_values.append(cv_sample.get("observation_quality"))
        fatigue_values.append(cv_sample.get("fatigue_score"))
        _count_key(fatigue_level_counts, cv_sample.get("fatigue_level"))

        evidence_codes = cv_sample.get("evidence_codes")
        if isinstance(evidence_codes, list):
            for code in evidence_codes:
                evidence_code_counts[str(code)] += 1

        reason = gate_result.get("reason")
        _count_key(gate_reason_counts, reason)
        if gate_result.get("should_trigger") is True:
            trigger_frames.append(
                {
                    "frame_id": frame.get("frame_id"),
                    "timestamp_ms": frame.get("timestamp_ms"),
                    "reason": str(reason) if reason is not None else "missing",
                }
            )

        if gate_state.get("vlm_enabled") is True:
            vlm_enabled_count += 1
        executed = gate_state.get("vlm_executed") is True
        if executed:
            vlm_executed_count += 1
        if _has_vlm_result(row.get("vlm_result")):
            vlm_result_count += 1
        elif executed:
            missing_result_after_execution_count += 1
        if gate_state.get("vlm_suppressed_by_cooldown") is True:
            cooldown_count += 1
        latency_values.append(gate_state.get("vlm_elapsed_seconds"))

    quality_numeric = _numeric_values(quality_values)
    quality_summary = _numeric_summary(quality_numeric)
    low_quality_frames = sum(1 for value in quality_numeric if value < quality_threshold)
    quality_summary.update(
        {
            "quality_threshold": quality_threshold,
            "low_quality_frames": low_quality_frames,
            "low_quality_ratio": _ratio(low_quality_frames, len(quality_numeric)),
        }
    )

    fatigue_numeric = _numeric_values(fatigue_values)
    fatigue_summary = _numeric_summary(fatigue_numeric)
    fatigue_summary.update(
        {
            "fatigue_level_counts": dict(fatigue_level_counts),
            "evidence_code_counts": dict(evidence_code_counts),
        }
    )

    latency_numeric = _numeric_values(latency_values)
    latency_summary = _numeric_summary(latency_numeric)

    return {
        "schema_version": SCHEMA_VERSION,
        "input": {
            "path": str(trace_path),
            "file_name": trace_path.name,
        },
        "frame_summary": {
            "total_rows": total_rows,
            "first_frame_id": first_frame.get("frame_id"),
            "last_frame_id": last_frame.get("frame_id"),
            "first_timestamp_ms": first_timestamp,
            "last_timestamp_ms": last_timestamp,
            "duration_ms": duration_ms,
            "timestamps_monotonic": timestamps_monotonic,
        },
        "face_summary": {
            "valid_face_frames": valid_face_frames,
            "valid_face_ratio": _ratio(valid_face_frames, total_rows),
            "presence_state_counts": dict(presence_counts),
        },
        "quality_summary": quality_summary,
        "fatigue_summary": fatigue_summary,
        "gate_summary": {
            "trigger_frame_count": len(trigger_frames),
            "trigger_frame_ratio": _ratio(len(trigger_frames), total_rows),
            "reason_counts": dict(gate_reason_counts),
            "trigger_frames": trigger_frames,
        },
        "vlm_summary": {
            "enabled_frame_count": vlm_enabled_count,
            "executed_frame_count": vlm_executed_count,
            "result_frame_count": vlm_result_count,
            "suppressed_by_cooldown_count": cooldown_count,
            "missing_result_after_execution_count": missing_result_after_execution_count,
            "latency_sample_count": latency_summary["numeric_sample_count"],
            "latency_seconds_mean": latency_summary["mean"],
            "latency_seconds_minimum": latency_summary["minimum"],
            "latency_seconds_maximum": latency_summary["maximum"],
        },
        "missing_data": missing_data,
    }


def _percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _number(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _counts_text(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return " ".join(f"{key}={value}" for key, value in counts.items())


def format_terminal_summary(report: dict[str, Any]) -> str:
    frame = report["frame_summary"]
    face = report["face_summary"]
    quality = report["quality_summary"]
    fatigue = report["fatigue_summary"]
    gate = report["gate_summary"]
    vlm = report["vlm_summary"]

    quality_line = "Observation quality: numeric=0"
    if quality["numeric_sample_count"]:
        quality_line = (
            "Observation quality: "
            f"mean={_number(quality['mean'])} "
            f"min={_number(quality['minimum'])} "
            f"max={_number(quality['maximum'])} "
            f"low={quality['low_quality_frames']}/{quality['numeric_sample_count']}"
        )

    fatigue_line = "CV fatigue score: numeric=0"
    if fatigue["numeric_sample_count"]:
        fatigue_line = (
            "CV fatigue score: "
            f"mean={_number(fatigue['mean'])} "
            f"min={_number(fatigue['minimum'])} "
            f"max={_number(fatigue['maximum'])} "
            f"numeric={fatigue['numeric_sample_count']}"
        )

    return "\n".join(
        [
            "Route A baseline summary",
            f"Input: {report['input']['path']}",
            f"Frames: {frame['total_rows']}",
            (
                "Timeline: "
                f"{_number(frame['first_timestamp_ms'])} ms -> "
                f"{_number(frame['last_timestamp_ms'])} ms "
                f"({_number(frame['duration_ms'])} ms)"
            ),
            (
                "Valid face frames: "
                f"{face['valid_face_frames']}/{frame['total_rows']} "
                f"({_percent(face['valid_face_ratio'])})"
            ),
            quality_line,
            fatigue_line,
            (
                "Gate trigger frames: "
                f"{gate['trigger_frame_count']}/{frame['total_rows']} "
                f"({_percent(gate['trigger_frame_ratio'])})"
            ),
            f"Gate reasons: {_counts_text(gate['reason_counts'])}",
            (
                "VLM: "
                f"executed={vlm['executed_frame_count']} "
                f"results={vlm['result_frame_count']} "
                f"cooldown_suppressed={vlm['suppressed_by_cooldown_count']}"
            ),
        ]
    )


def write_report(report: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a Route A JSONL trace.")
    parser.add_argument("--input", required=True, help="Path to the Route A trace JSONL file.")
    parser.add_argument("--output", required=True, help="Path to write the structured JSON report.")
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=0.5,
        help="Observation-quality threshold for low-quality frame counting.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows = load_trace_rows(args.input)
        report = summarize_trace(rows, args.input, quality_threshold=args.quality_threshold)
        write_report(report, args.output)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(format_terminal_summary(report))
    print(f"Report written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
