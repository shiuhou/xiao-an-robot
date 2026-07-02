#!/usr/bin/env python
"""Event-level evaluation of Route A traces against human annotations."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import statistics
import sys
from typing import Any


SCHEMA_VERSION = "route_a_event_eval_v0.1"
VALID_EVENTS = {"long_eye_closure", "yawn", "normal"}
REQUIRED_COLUMNS = {"clip_id", "start_sec", "end_sec", "observable_event"}
GATE_REASON_MATCH_EYE = {"high_fatigue", "fatigue"}
GATE_REASON_MATCH_YAWN = {"high_fatigue", "yawn", "fatigue"}
UNEXPECTED_EVIDENCE_IN_NORMAL = {"LONG_CLOSURE", "YAWN", "PERCLOS_HIGH", "PERCLOS_MID"}


def load_annotations(path: str | Path) -> list[dict[str, Any]]:
    ann_path = Path(path)
    if not ann_path.exists():
        raise ValueError(f"annotations file does not exist: {ann_path}")
    rows: list[dict[str, Any]] = []
    with ann_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"annotations file is empty: {ann_path}")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"annotations CSV missing columns: {sorted(missing)}"
            )
        for i, row in enumerate(reader, start=2):
            event = row["observable_event"]
            if event not in VALID_EVENTS:
                raise ValueError(
                    f"annotations line {i}: unknown event '{event}'"
                )
            rows.append({
                "clip_id": row["clip_id"],
                "start_sec": float(row["start_sec"]),
                "end_sec": float(row["end_sec"]),
                "observable_event": event,
            })
    if not rows:
        raise ValueError(f"annotations file has no data rows: {ann_path}")
    return rows


def load_trace(path: str | Path) -> list[dict[str, Any]]:
    trace_path = Path(path)
    if not trace_path.exists():
        raise ValueError(f"trace file does not exist: {trace_path}")
    rows: list[dict[str, Any]] = []
    with trace_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSONL parse error on line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"JSONL parse error on line {line_number}: expected object"
                )
            rows.append(parsed)
    if not rows:
        raise ValueError(f"trace file is empty: {trace_path}")
    return rows


def group_annotations_by_clip(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["clip_id"], []).append(row)
    return groups


def _section(row: dict[str, Any], key: str) -> dict[str, Any]:
    v = row.get(key)
    return v if isinstance(v, dict) else {}


def _timestamp_sec(row: dict[str, Any]) -> float:
    frame = _section(row, "frame")
    ts = frame.get("timestamp_ms")
    if ts is None:
        return 0.0
    return float(ts) / 1000.0


def _frames_in_window(
    trace_rows: list[dict[str, Any]],
    start_sec: float,
    end_sec: float,
) -> list[dict[str, Any]]:
    result = []
    for row in trace_rows:
        ts = _timestamp_sec(row)
        if start_sec <= ts <= end_sec:
            result.append(row)
    return result


def merge_false_trigger_episodes(
    trigger_rows: list[tuple[float, str]],
    max_gap_seconds: float = 0.5,
) -> list[dict[str, Any]]:
    if not trigger_rows:
        return []
    sorted_rows = sorted(trigger_rows, key=lambda x: x[0])
    episodes: list[dict[str, Any]] = []
    ep_start = sorted_rows[0][0]
    ep_end = sorted_rows[0][0]
    reason_counts: Counter[str] = Counter()
    reason_counts[sorted_rows[0][1]] += 1

    for ts, reason in sorted_rows[1:]:
        if ts - ep_end <= max_gap_seconds:
            ep_end = ts
            reason_counts[reason] += 1
        else:
            episodes.append({
                "start_sec": round(ep_start, 3),
                "end_sec": round(ep_end, 3),
                "duration_sec": round(ep_end - ep_start, 3),
                "reason_counts": dict(reason_counts),
            })
            ep_start = ts
            ep_end = ts
            reason_counts = Counter()
            reason_counts[reason] += 1

    episodes.append({
        "start_sec": round(ep_start, 3),
        "end_sec": round(ep_end, 3),
        "duration_sec": round(ep_end - ep_start, 3),
        "reason_counts": dict(reason_counts),
    })
    return episodes


def evaluate_event(
    annotation: dict[str, Any],
    trace_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    warmup = config["warmup_seconds"]
    tolerance = config["tolerance_seconds"]
    event_type = annotation["observable_event"]
    start = annotation["start_sec"]
    end = annotation["end_sec"]

    effective_start = max(start, warmup)
    effective_end = end
    partially_excluded = effective_start > start
    entirely_within_warmup = effective_start >= effective_end

    result: dict[str, Any] = {
        "clip_id": annotation["clip_id"],
        "event_type": event_type,
        "start_sec": start,
        "end_sec": end,
        "effective_start_sec": round(effective_start, 3),
        "effective_end_sec": round(effective_end, 3),
        "partially_excluded_by_warmup": partially_excluded,
    }

    if entirely_within_warmup:
        result["evaluable"] = False
        result["excluded_reason"] = "entirely_within_warmup"
        return result

    result["evaluable"] = True

    window_start = max(effective_start - tolerance, warmup)
    window_end = effective_end + tolerance

    window_frames = _frames_in_window(trace_rows, window_start, window_end)

    # Check for preexisting gate trigger
    pre_frames = _frames_in_window(
        trace_rows,
        max(effective_start - tolerance - 0.001, warmup),
        effective_start - 0.001,
    )
    preexisting_trigger = False
    for pf in pre_frames:
        gr = _section(pf, "gate_result")
        if gr.get("should_trigger") is True:
            preexisting_trigger = True
            break

    if event_type == "long_eye_closure":
        result.update(_evaluate_eye_closure(
            window_frames, effective_start, preexisting_trigger,
        ))
    elif event_type == "yawn":
        result.update(_evaluate_yawn(
            window_frames, effective_start, preexisting_trigger,
        ))

    return result


def _evaluate_eye_closure(
    window_frames: list[dict[str, Any]],
    effective_start: float,
    preexisting_trigger: bool,
) -> dict[str, Any]:
    evidence_hit = False
    high_fatigue_hit = False
    cv_first_sec: float | None = None
    gate_triggered_any = False
    gate_reason_match = False
    gate_first_sec: float | None = None
    matched_reasons: Counter[str] = Counter()

    for row in window_frames:
        cs = _section(row, "cv_sample")
        gr = _section(row, "gate_result")
        ts = _timestamp_sec(row)

        codes = cs.get("evidence_codes", [])
        if isinstance(codes, list) and "LONG_CLOSURE" in codes:
            evidence_hit = True
            if cv_first_sec is None or ts < cv_first_sec:
                cv_first_sec = ts

        if cs.get("fatigue_level") == "high":
            high_fatigue_hit = True
            if cv_first_sec is None or ts < cv_first_sec:
                cv_first_sec = ts

        if gr.get("should_trigger") is True:
            gate_triggered_any = True
            reason = gr.get("reason", "")
            matched_reasons[reason] += 1
            if reason in GATE_REASON_MATCH_EYE:
                gate_reason_match = True
                if gate_first_sec is None or ts < gate_first_sec:
                    gate_first_sec = ts

    cv_detected = evidence_hit or high_fatigue_hit

    cv_latency = None
    if cv_first_sec is not None and cv_first_sec >= effective_start:
        cv_latency = round(cv_first_sec - effective_start, 3)

    gate_latency = None
    if gate_first_sec is not None and gate_first_sec >= effective_start:
        gate_latency = round(gate_first_sec - effective_start, 3)

    detection_ambiguous = preexisting_trigger and gate_triggered_any

    return {
        "cv_detected": cv_detected,
        "cv_evidence_hit": evidence_hit,
        "cv_high_fatigue_hit": high_fatigue_hit,
        "cv_first_detection_sec": round(cv_first_sec, 3) if cv_first_sec is not None else None,
        "cv_latency_sec": cv_latency,
        "gate_triggered_any": gate_triggered_any,
        "gate_reason_match": gate_reason_match,
        "gate_first_trigger_sec": round(gate_first_sec, 3) if gate_first_sec is not None else None,
        "gate_latency_sec": gate_latency,
        "preexisting_gate_trigger": preexisting_trigger,
        "detection_ambiguous_due_to_preexisting_trigger": detection_ambiguous,
        "matched_gate_reasons": dict(matched_reasons),
    }


def _evaluate_yawn(
    window_frames: list[dict[str, Any]],
    effective_start: float,
    preexisting_trigger: bool,
) -> dict[str, Any]:
    cv_detected = False
    cv_first_sec: float | None = None
    gate_triggered_any = False
    gate_reason_match = False
    gate_first_sec: float | None = None
    matched_reasons: Counter[str] = Counter()

    for row in window_frames:
        cs = _section(row, "cv_sample")
        gr = _section(row, "gate_result")
        ts = _timestamp_sec(row)

        codes = cs.get("evidence_codes", [])
        if isinstance(codes, list) and "YAWN" in codes:
            cv_detected = True
            if cv_first_sec is None or ts < cv_first_sec:
                cv_first_sec = ts

        if gr.get("should_trigger") is True:
            gate_triggered_any = True
            reason = gr.get("reason", "")
            matched_reasons[reason] += 1
            if reason in GATE_REASON_MATCH_YAWN:
                gate_reason_match = True
                if gate_first_sec is None or ts < gate_first_sec:
                    gate_first_sec = ts

    cv_latency = None
    if cv_first_sec is not None and cv_first_sec >= effective_start:
        cv_latency = round(cv_first_sec - effective_start, 3)

    gate_latency = None
    if gate_first_sec is not None and gate_first_sec >= effective_start:
        gate_latency = round(gate_first_sec - effective_start, 3)

    detection_ambiguous = preexisting_trigger and gate_triggered_any

    return {
        "cv_detected": cv_detected,
        "cv_evidence_hit": cv_detected,
        "cv_high_fatigue_hit": False,
        "cv_first_detection_sec": round(cv_first_sec, 3) if cv_first_sec is not None else None,
        "cv_latency_sec": cv_latency,
        "gate_triggered_any": gate_triggered_any,
        "gate_reason_match": gate_reason_match,
        "gate_first_trigger_sec": round(gate_first_sec, 3) if gate_first_sec is not None else None,
        "gate_latency_sec": gate_latency,
        "preexisting_gate_trigger": preexisting_trigger,
        "detection_ambiguous_due_to_preexisting_trigger": detection_ambiguous,
        "matched_gate_reasons": dict(matched_reasons),
    }


def evaluate_normal_interval(
    annotation: dict[str, Any],
    trace_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    warmup = config["warmup_seconds"]
    episode_gap = config["false_trigger_episode_gap_seconds"]
    start = annotation["start_sec"]
    end = annotation["end_sec"]
    effective_start = max(start, warmup)
    effective_end = end

    if effective_start >= effective_end:
        return {
            "start_sec": start,
            "end_sec": end,
            "effective_start_sec": round(effective_start, 3),
            "effective_end_sec": round(effective_end, 3),
            "evaluable": False,
            "excluded_reason": "entirely_within_warmup",
        }

    frames = _frames_in_window(trace_rows, effective_start, effective_end)
    frame_count = len(frames)

    false_trigger_rows: list[tuple[float, str]] = []
    high_fatigue_count = 0
    unexpected_evidence: Counter[str] = Counter()

    for row in frames:
        cs = _section(row, "cv_sample")
        gr = _section(row, "gate_result")
        ts = _timestamp_sec(row)

        if gr.get("should_trigger") is True:
            reason = gr.get("reason", "missing")
            false_trigger_rows.append((ts, reason))

        if cs.get("fatigue_level") == "high":
            high_fatigue_count += 1

        codes = cs.get("evidence_codes", [])
        if isinstance(codes, list):
            for code in codes:
                if code in UNEXPECTED_EVIDENCE_IN_NORMAL:
                    unexpected_evidence[code] += 1

    episodes = merge_false_trigger_episodes(false_trigger_rows, episode_gap)

    return {
        "start_sec": start,
        "end_sec": end,
        "effective_start_sec": round(effective_start, 3),
        "effective_end_sec": round(effective_end, 3),
        "frame_count": frame_count,
        "false_trigger_frame_count": len(false_trigger_rows),
        "false_trigger_frame_ratio": (
            round(len(false_trigger_rows) / frame_count, 4)
            if frame_count > 0 else 0.0
        ),
        "false_trigger_episode_count": len(episodes),
        "false_trigger_episodes": episodes,
        "high_fatigue_frame_count": high_fatigue_count,
        "unexpected_evidence_code_counts": dict(unexpected_evidence),
    }


def evaluate_clip(
    clip_id: str,
    annotations: list[dict[str, Any]],
    trace_rows: list[dict[str, Any]],
    trace_path: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    warmup = config["warmup_seconds"]
    warmup_frames = [
        r for r in trace_rows if _timestamp_sec(r) < warmup
    ]

    events = []
    normal_intervals = []

    for ann in annotations:
        if ann["observable_event"] == "normal":
            normal_intervals.append(
                evaluate_normal_interval(ann, trace_rows, config)
            )
        else:
            events.append(evaluate_event(ann, trace_rows, config))

    return {
        "trace_path": trace_path,
        "annotation_count": len(annotations),
        "excluded_warmup_frame_count": len(warmup_frames),
        "events": events,
        "normal_intervals": normal_intervals,
    }


def _safe_div(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.fmean(values), 3)


def aggregate_results(clips: dict[str, dict[str, Any]]) -> dict[str, Any]:
    eye_annotated = 0
    eye_evaluable = 0
    eye_cv_detected = 0
    eye_gate_matched = 0
    eye_cv_latencies: list[float] = []
    eye_gate_latencies: list[float] = []

    yawn_annotated = 0
    yawn_evaluable = 0
    yawn_cv_detected = 0
    yawn_gate_matched = 0
    yawn_cv_latencies: list[float] = []
    yawn_gate_latencies: list[float] = []

    normal_interval_count = 0
    normal_frame_count = 0
    normal_false_trigger_frames = 0
    normal_false_trigger_episodes = 0

    for clip in clips.values():
        for ev in clip["events"]:
            etype = ev["event_type"]
            if etype == "long_eye_closure":
                eye_annotated += 1
                if ev.get("evaluable"):
                    eye_evaluable += 1
                    if ev["cv_detected"]:
                        eye_cv_detected += 1
                    if ev["gate_reason_match"]:
                        eye_gate_matched += 1
                    if ev["cv_latency_sec"] is not None:
                        eye_cv_latencies.append(ev["cv_latency_sec"])
                    if ev["gate_latency_sec"] is not None:
                        eye_gate_latencies.append(ev["gate_latency_sec"])
            elif etype == "yawn":
                yawn_annotated += 1
                if ev.get("evaluable"):
                    yawn_evaluable += 1
                    if ev["cv_detected"]:
                        yawn_cv_detected += 1
                    if ev["gate_reason_match"]:
                        yawn_gate_matched += 1
                    if ev["cv_latency_sec"] is not None:
                        yawn_cv_latencies.append(ev["cv_latency_sec"])
                    if ev["gate_latency_sec"] is not None:
                        yawn_gate_latencies.append(ev["gate_latency_sec"])

        for ni in clip["normal_intervals"]:
            if ni.get("evaluable") is False:
                continue
            normal_interval_count += 1
            normal_frame_count += ni["frame_count"]
            normal_false_trigger_frames += ni["false_trigger_frame_count"]
            normal_false_trigger_episodes += ni["false_trigger_episode_count"]

    return {
        "event_count_total": eye_annotated + yawn_annotated,
        "event_count_evaluable": eye_evaluable + yawn_evaluable,
        "long_eye_closure": {
            "annotated": eye_annotated,
            "evaluable": eye_evaluable,
            "cv_detected": eye_cv_detected,
            "cv_event_recall": _safe_div(eye_cv_detected, eye_evaluable),
            "gate_reason_matched": eye_gate_matched,
            "gate_event_recall": _safe_div(eye_gate_matched, eye_evaluable),
            "latency_sample_count": len(eye_cv_latencies),
            "mean_cv_latency_sec": _safe_mean(eye_cv_latencies),
            "mean_gate_latency_sec": _safe_mean(eye_gate_latencies),
        },
        "yawn": {
            "annotated": yawn_annotated,
            "evaluable": yawn_evaluable,
            "cv_detected": yawn_cv_detected,
            "cv_event_recall": _safe_div(yawn_cv_detected, yawn_evaluable),
            "gate_reason_matched": yawn_gate_matched,
            "gate_event_recall": _safe_div(yawn_gate_matched, yawn_evaluable),
            "latency_sample_count": len(yawn_cv_latencies),
            "mean_cv_latency_sec": _safe_mean(yawn_cv_latencies),
            "mean_gate_latency_sec": _safe_mean(yawn_gate_latencies),
        },
        "normal": {
            "normal_interval_count": normal_interval_count,
            "normal_frame_count": normal_frame_count,
            "false_trigger_frame_count": normal_false_trigger_frames,
            "false_trigger_frame_ratio": _safe_div(
                normal_false_trigger_frames, normal_frame_count,
            ),
            "false_trigger_episode_count": normal_false_trigger_episodes,
        },
    }


def format_terminal_summary(report: dict[str, Any]) -> str:
    agg = report["aggregate"]
    cfg = report["config"]
    lines = [
        "Route A event evaluation",
        f"Annotations: {report.get('annotations_path', 'n/a')}",
        f"Warmup excluded: first {cfg['warmup_seconds']} s",
        "",
    ]

    for label, key in [
        ("Long eye closure", "long_eye_closure"),
        ("Yawn", "yawn"),
    ]:
        s = agg[key]
        lines.append(f"{label}:")
        lines.append(f"  Evaluable events: {s['evaluable']}")
        lines.append(
            f"  CV detected: {s['cv_detected']}/{s['evaluable']}"
        )
        lines.append(
            f"  Gate reason matched: {s['gate_reason_matched']}/{s['evaluable']}"
        )
        if s["mean_cv_latency_sec"] is not None:
            lines.append(
                f"  Mean CV latency: {s['mean_cv_latency_sec']:.2f} s"
            )
        if s["mean_gate_latency_sec"] is not None:
            lines.append(
                f"  Mean Gate latency: {s['mean_gate_latency_sec']:.2f} s"
            )
        lines.append("")

    n = agg["normal"]
    lines.append("Normal intervals:")
    lines.append(f"  Frames: {n['normal_frame_count']}")
    lines.append(
        f"  False trigger frames: {n['false_trigger_frame_count']}"
    )
    lines.append(
        f"  False trigger episodes: {n['false_trigger_episode_count']}"
    )
    ratio = n["false_trigger_frame_ratio"]
    ratio_str = f"{ratio * 100:.2f}%" if ratio is not None else "n/a"
    lines.append(f"  False trigger ratio: {ratio_str}")

    return "\n".join(lines)


def write_report(report: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Route A traces against human annotations.",
    )
    parser.add_argument(
        "--annotations", required=True,
        help="Path to the annotations CSV file.",
    )
    parser.add_argument(
        "--traces-dir", required=True,
        help="Directory containing Route A JSONL traces.",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write the evaluation JSON report.",
    )
    parser.add_argument(
        "--warmup-seconds", type=float, default=5.0,
        help="Warmup period in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--tolerance-seconds", type=float, default=0.2,
        help="Time tolerance in seconds for event matching (default: 0.2).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    traces_dir = Path(args.traces_dir)
    config = {
        "warmup_seconds": args.warmup_seconds,
        "tolerance_seconds": args.tolerance_seconds,
        "false_trigger_episode_gap_seconds": 0.5,
    }

    try:
        annotations = load_annotations(args.annotations)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    grouped = group_annotations_by_clip(annotations)
    clips: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for clip_id, clip_annotations in sorted(grouped.items()):
        trace_path = traces_dir / f"{clip_id}.jsonl"
        if not trace_path.exists():
            errors.append(
                f"missing trace for clip '{clip_id}': {trace_path}"
            )
            continue
        try:
            trace_rows = load_trace(trace_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        clips[clip_id] = evaluate_clip(
            clip_id, clip_annotations, trace_rows, str(trace_path), config,
        )

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1

    agg = aggregate_results(clips)

    report = {
        "schema_version": SCHEMA_VERSION,
        "annotations_path": args.annotations,
        "config": config,
        "clips": clips,
        "aggregate": agg,
    }

    try:
        write_report(report, args.output)
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 1

    print(format_terminal_summary(report))
    print(f"\nReport written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
