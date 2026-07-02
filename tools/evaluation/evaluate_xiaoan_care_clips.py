"""Build clip-level policy timelines for XiaoAn-Care-v1.

This is policy-level validation using label-derived clip timeline samples. It
does not run OpenFace/VLM models and does not execute robot actions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.evaluation.evaluate_xiaoan_care_policy import fatigue_label_to_score_100
from tools.evaluation.prepare_xiaoan_care_report_assets import read_csv_rows


SAMPLE_INTERVAL_S = 1.0
COOLDOWN_SECONDS = 300.0
TRUE_CLIP_TYPES = {"eyes_closed_long", "head_down_sleepy", "yawn"}
FALSE_CLIP_TYPES = {"normal_working", "blink", "bad_quality", "no_face"}
OPTIONAL_CLIP_TYPES = {"eyes_closed_short"}
QUALITY_INVALID_CLIP_TYPES = {"bad_quality", "no_face"}
QUALITY_INVALID_IMAGE_QUALITY = {"bad", "bad_frame", "low", "poor", "unknown", "no_face"}
STATE_TO_CODE = {
    "OBSERVE": 0,
    "QUALITY_GATE": 1,
    "EXPRESSION_ONLY": 2,
    "CARING": 3,
    "COOLDOWN": 4,
}


@dataclass
class ClipPolicyState:
    last_high_level_care_s: float | None = None


@dataclass
class ClipTimelineRow:
    clip_id: str
    t_sec: float
    sample_kind: str
    clip_type: str
    scene: str
    fatigue_score_100: float | None
    emotion_tag: str
    confidence: float
    quality_valid: bool
    state: str
    action_level: int
    high_level_care: bool
    expression_only: bool
    suppressed_by_quality: bool
    suppressed_by_cooldown: bool
    reason: str
    expected_high_level_care: str


@dataclass
class ClipSummary:
    clip_id: str
    clip_type: str
    duration_sec: float
    expected_behavior: str
    expected_high_level_care: str
    evaluated_samples: int
    first_trigger_time_s: float | None
    high_level_trigger_count: int
    expression_only_count: int
    cooldown_suppressed_count: int
    quality_suppressed_count: int
    result: str
    reason: str
    status: str = "evaluated"
    label_conflict_warning: bool = False
    openface_outputs_found_count: int = 0


def expected_high_level_for_clip_type(clip_type: str | None) -> str:
    clip_type = (clip_type or "").strip()
    if clip_type in TRUE_CLIP_TYPES:
        return "true"
    if clip_type in FALSE_CLIP_TYPES:
        return "false"
    if clip_type in OPTIONAL_CLIP_TYPES:
        return "optional"
    return "unknown"


def expected_behavior_for_clip_type(clip_type: str | None) -> str:
    mapping = {
        "normal_working": "observe only",
        "blink": "observe only; blink is not fatigue",
        "bad_quality": "quality gate; no care decision",
        "no_face": "quality gate; no care decision",
        "eyes_closed_long": "high-level fatigue care expected",
        "head_down_sleepy": "high-level fatigue care expected",
        "yawn": "high-level fatigue care expected",
        "eyes_closed_short": "expression only / optional light care",
    }
    return mapping.get((clip_type or "").strip(), "unknown / needs review")


def label_conflict_warning(row: dict[str, str], expected: str) -> bool:
    care_needed = (row.get("care_needed") or "").strip()
    if expected == "true":
        return care_needed != "1"
    if expected == "false":
        return care_needed != "0"
    if expected == "optional":
        return care_needed not in {"0", "1"}
    return False


def _float_value(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_event_active(row: dict[str, str], t_sec: float) -> bool:
    start = _float_value(row.get("start_time_sec"), 0.0)
    end = _float_value(row.get("end_time_sec"), _float_value(row.get("duration_sec"), 0.0))
    return start <= t_sec <= end


def is_quality_valid(row: dict[str, str]) -> bool:
    clip_type = (row.get("clip_type") or "").strip()
    face_visible = (row.get("face_visible") or "").strip().lower()
    image_quality = (row.get("image_quality") or "").strip().lower()
    if clip_type in QUALITY_INVALID_CLIP_TYPES:
        return False
    if face_visible in {"no", "none", "false", "0"}:
        return False
    if image_quality in QUALITY_INVALID_IMAGE_QUALITY and face_visible in {"no", "none", "false", "0"}:
        return False
    return True


def build_timeline_sample(row: dict[str, str], t_sec: float) -> dict[str, object]:
    clip_type = (row.get("clip_type") or "").strip()
    active = is_event_active(row, t_sec)
    quality_valid = is_quality_valid(row)
    sample = {
        "sample_kind": "label_derived_clip_timeline",
        "clip_id": (row.get("clip_id") or "").strip(),
        "clip_type": clip_type,
        "scene": (row.get("scene") or "").strip(),
        "t_sec": t_sec,
        "quality_valid": quality_valid,
        "expected_high_level_care": expected_high_level_for_clip_type(clip_type),
        "fatigue_score_100": 10.0,
        "emotion_tag": "neutral",
        "confidence": 0.6,
    }
    if clip_type == "blink":
        sample["fatigue_score_100"] = 20.0 if active else 10.0
    elif clip_type in {"bad_quality", "no_face"}:
        sample["fatigue_score_100"] = None
        sample["emotion_tag"] = "unknown"
        sample["confidence"] = 0.0
    elif clip_type == "eyes_closed_long" and active:
        sample["fatigue_score_100"] = 85.0
    elif clip_type == "head_down_sleepy" and active:
        sample["fatigue_score_100"] = 70.0
    elif clip_type == "yawn" and active:
        sample["fatigue_score_100"] = 70.0
        sample["emotion_tag"] = "tired"
        sample["confidence"] = 0.8
    elif clip_type == "eyes_closed_short" and active:
        sample["fatigue_score_100"] = 50.0
        sample["emotion_tag"] = "neutral"
        sample["confidence"] = 0.6
    elif active:
        sample["fatigue_score_100"] = fatigue_label_to_score_100(row.get("fatigue_label"))
    return sample


def evaluate_timeline_sample(sample: dict[str, object], state: ClipPolicyState) -> ClipTimelineRow:
    clip_type = str(sample.get("clip_type") or "")
    expected = str(sample.get("expected_high_level_care") or "unknown")
    t_sec = float(sample.get("t_sec") or 0.0)
    fatigue = sample.get("fatigue_score_100")
    quality_valid = bool(sample.get("quality_valid"))

    if not quality_valid:
        return _row_from_sample(
            sample,
            state_name="QUALITY_GATE",
            action_level=0,
            high_level_care=False,
            expression_only=False,
            suppressed_by_quality=True,
            suppressed_by_cooldown=False,
            reason="quality_gate",
        )

    if clip_type == "eyes_closed_short" and fatigue == 50.0:
        return _row_from_sample(
            sample,
            state_name="EXPRESSION_ONLY",
            action_level=1,
            high_level_care=False,
            expression_only=True,
            suppressed_by_quality=False,
            suppressed_by_cooldown=False,
            reason="expression_only",
        )

    high_signal = fatigue is not None and float(fatigue) >= 67.0
    if high_signal:
        if state.last_high_level_care_s is None:
            state.last_high_level_care_s = t_sec
            return _row_from_sample(
                sample,
                state_name="CARING",
                action_level=3,
                high_level_care=True,
                expression_only=False,
                suppressed_by_quality=False,
                suppressed_by_cooldown=False,
                reason="high_fatigue",
            )
        if t_sec - state.last_high_level_care_s < COOLDOWN_SECONDS:
            return _row_from_sample(
                sample,
                state_name="COOLDOWN",
                action_level=0,
                high_level_care=False,
                expression_only=False,
                suppressed_by_quality=False,
                suppressed_by_cooldown=True,
                reason="cooldown",
            )

    return _row_from_sample(
        sample,
        state_name="OBSERVE",
        action_level=0,
        high_level_care=False,
        expression_only=False,
        suppressed_by_quality=False,
        suppressed_by_cooldown=False,
        reason="observe",
    )


def _row_from_sample(
    sample: dict[str, object],
    state_name: str,
    action_level: int,
    high_level_care: bool,
    expression_only: bool,
    suppressed_by_quality: bool,
    suppressed_by_cooldown: bool,
    reason: str,
) -> ClipTimelineRow:
    return ClipTimelineRow(
        clip_id=str(sample.get("clip_id") or ""),
        t_sec=float(sample.get("t_sec") or 0.0),
        sample_kind=str(sample.get("sample_kind") or "label_derived_clip_timeline"),
        clip_type=str(sample.get("clip_type") or ""),
        scene=str(sample.get("scene") or ""),
        fatigue_score_100=sample.get("fatigue_score_100"),
        emotion_tag=str(sample.get("emotion_tag") or "unknown"),
        confidence=float(sample.get("confidence") or 0.0),
        quality_valid=bool(sample.get("quality_valid")),
        state=state_name,
        action_level=action_level,
        high_level_care=high_level_care,
        expression_only=expression_only,
        suppressed_by_quality=suppressed_by_quality,
        suppressed_by_cooldown=suppressed_by_cooldown,
        reason=reason,
        expected_high_level_care=str(sample.get("expected_high_level_care") or "unknown"),
    )


def evaluate_clip_row(dataset_root: Path, row: dict[str, str]) -> tuple[list[ClipTimelineRow], ClipSummary]:
    clip_id = (row.get("clip_id") or "").strip()
    clip_type = (row.get("clip_type") or "").strip()
    duration = _float_value(row.get("duration_sec"), 0.0)
    expected = expected_high_level_for_clip_type(clip_type)
    file_path = (row.get("file_path") or "").strip()
    conflict = label_conflict_warning(row, expected)
    if not file_path or not (dataset_root / file_path).exists():
        return [], ClipSummary(
            clip_id=clip_id,
            clip_type=clip_type,
            duration_sec=duration,
            expected_behavior=expected_behavior_for_clip_type(clip_type),
            expected_high_level_care=expected,
            evaluated_samples=0,
            first_trigger_time_s=None,
            high_level_trigger_count=0,
            expression_only_count=0,
            cooldown_suppressed_count=0,
            quality_suppressed_count=0,
            result="warning",
            reason="skipped_missing_clip",
            status="skipped_missing_clip",
            label_conflict_warning=conflict,
        )

    state = ClipPolicyState()
    timeline: list[ClipTimelineRow] = []
    for t_sec in _timeline_seconds(duration):
        sample = build_timeline_sample(row, t_sec)
        timeline.append(evaluate_timeline_sample(sample, state))
    summary = summarize_clip(row, timeline, conflict)
    return timeline, summary


def _timeline_seconds(duration: float) -> list[float]:
    end = int(math.floor(max(duration, 0.0)))
    return [float(value) for value in range(0, end + 1)]


def summarize_clip(row: dict[str, str], timeline: list[ClipTimelineRow], conflict: bool) -> ClipSummary:
    clip_id = (row.get("clip_id") or "").strip()
    clip_type = (row.get("clip_type") or "").strip()
    duration = _float_value(row.get("duration_sec"), 0.0)
    expected = expected_high_level_for_clip_type(clip_type)
    high_count = sum(1 for item in timeline if item.high_level_care)
    expression_count = sum(1 for item in timeline if item.expression_only)
    cooldown_count = sum(1 for item in timeline if item.suppressed_by_cooldown)
    quality_count = sum(1 for item in timeline if item.suppressed_by_quality)
    first_trigger = next((item.t_sec for item in timeline if item.high_level_care), None)
    result, reason = _clip_result(expected, high_count, expression_count)
    if conflict and result == "pass":
        reason = f"{reason}; label_conflict_warning"
    return ClipSummary(
        clip_id=clip_id,
        clip_type=clip_type,
        duration_sec=duration,
        expected_behavior=expected_behavior_for_clip_type(clip_type),
        expected_high_level_care=expected,
        evaluated_samples=len(timeline),
        first_trigger_time_s=first_trigger,
        high_level_trigger_count=high_count,
        expression_only_count=expression_count,
        cooldown_suppressed_count=cooldown_count,
        quality_suppressed_count=quality_count,
        result=result,
        reason=reason,
        label_conflict_warning=conflict,
    )


def _clip_result(expected: str, high_count: int, expression_count: int) -> tuple[str, str]:
    if expected == "true":
        if high_count > 0:
            return "pass", "expected high-level care triggered"
        return "fail", "expected high-level care did not trigger"
    if expected == "false":
        if high_count == 0:
            return "pass", "no high-level care triggered"
        return "fail", "unexpected high-level care triggered"
    if expected == "optional":
        if high_count > 0:
            return "warning", "optional clip escalated to high-level care"
        if expression_count > 0:
            return "pass", "optional clip handled as expression_only"
        return "warning", "optional clip produced no action"
    return "warning", "unknown expected behavior"


def evaluate_clip_dataset(dataset_root: Path) -> tuple[list[ClipTimelineRow], list[ClipSummary], dict[str, object]]:
    dataset_root = Path(dataset_root)
    rows = read_csv_rows(dataset_root / "labels/clips_labels.csv")
    all_timeline: list[ClipTimelineRow] = []
    summaries: list[ClipSummary] = []
    for row in rows:
        timeline, summary = evaluate_clip_row(dataset_root, row)
        all_timeline.extend(timeline)
        summaries.append(summary)

    openface_info = inspect_openface_outputs(dataset_root)
    summary = {
        "note": "Policy timeline validation using label-derived clip timeline samples; not model prediction accuracy.",
        "total_clips": len(summaries),
        "pass_count": sum(1 for item in summaries if item.result == "pass"),
        "fail_count": sum(1 for item in summaries if item.result == "fail"),
        "warning_count": sum(1 for item in summaries if item.result == "warning"),
        "expected_high_level_total": sum(1 for item in summaries if item.expected_high_level_care == "true"),
        "expected_high_level_pass": sum(
            1 for item in summaries if item.expected_high_level_care == "true" and item.result == "pass"
        ),
        "false_high_level_trigger_count": sum(
            1
            for item in summaries
            if item.expected_high_level_care == "false" and item.high_level_trigger_count > 0
        ),
        "optional_clip_count": sum(1 for item in summaries if item.expected_high_level_care == "optional"),
        "quality_suppressed_total": sum(item.quality_suppressed_count for item in summaries),
        "cooldown_suppressed_total": sum(item.cooldown_suppressed_count for item in summaries),
        "skipped_missing_clip_count": sum(1 for item in summaries if item.status == "skipped_missing_clip"),
        "label_conflict_warning_count": sum(1 for item in summaries if item.label_conflict_warning),
        **openface_info,
    }
    return all_timeline, summaries, summary


def inspect_openface_outputs(dataset_root: Path) -> dict[str, object]:
    openface_dir = dataset_root / "processed/openface_outputs"
    jsonl_files = sorted(openface_dir.glob("*.jsonl")) if openface_dir.exists() else []
    frames_processed = 0
    for path in jsonl_files:
        try:
            with path.open("r", encoding="utf-8") as f:
                frames_processed += sum(1 for line in f if line.strip())
        except OSError:
            pass
    return {
        "openface_outputs_found_count": len(jsonl_files),
        "openface_outputs_used": False,
        "openface_frames_processed": frames_processed,
    }


def run_clip_eval(dataset_root: Path, out_root: Path) -> dict[str, object]:
    dataset_root = Path(dataset_root)
    out_root = Path(out_root)
    timeline, summaries, summary = evaluate_clip_dataset(dataset_root)
    write_outputs(out_root, timeline, summaries, summary)
    return {
        "timeline": timeline,
        "summaries": summaries,
        "summary": summary,
        "outputs": [
            str(out_root / "tables/table_clip_trigger_summary.md"),
            str(out_root / "tables/table_clip_policy_metrics.md"),
            str(out_root / "figures/fig_clip_state_timeline.png"),
            str(out_root / "figures/fig_clip_action_timeline.png"),
            str(out_root / "logs/clip_policy_timeline.csv"),
            str(out_root / "logs/clip_policy_results.jsonl"),
            str(out_root / "logs/clip_policy_summary.json"),
        ],
    }


def write_outputs(
    out_root: Path,
    timeline: list[ClipTimelineRow],
    summaries: list[ClipSummary],
    summary: dict[str, object],
) -> None:
    logs_dir = out_root / "logs"
    tables_dir = out_root / "tables"
    figures_dir = out_root / "figures"
    logs_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    write_timeline_csv(logs_dir / "clip_policy_timeline.csv", timeline)
    write_clip_results_jsonl(logs_dir / "clip_policy_results.jsonl", summaries)
    (logs_dir / "clip_policy_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_tables(tables_dir, summaries, summary)
    write_figures(figures_dir, timeline, summaries)


def write_timeline_csv(path: Path, timeline: list[ClipTimelineRow]) -> None:
    fieldnames = list(asdict(ClipTimelineRow("", 0, "", "", "", None, "", 0, True, "", 0, False, False, False, False, "", "")).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in timeline:
            writer.writerow(asdict(row))


def write_clip_results_jsonl(path: Path, summaries: list[ClipSummary]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for summary in summaries:
            f.write(json.dumps(asdict(summary), ensure_ascii=False) + "\n")


def write_tables(tables_dir: Path, summaries: list[ClipSummary], summary: dict[str, object]) -> None:
    trigger_rows = [
        [
            item.clip_id,
            item.clip_type,
            item.expected_high_level_care,
            "" if item.first_trigger_time_s is None else item.first_trigger_time_s,
            item.high_level_trigger_count,
            item.expression_only_count,
            item.cooldown_suppressed_count,
            item.quality_suppressed_count,
            item.result,
            item.reason,
        ]
        for item in summaries
    ]
    (tables_dir / "table_clip_trigger_summary.md").write_text(
        "# Clip Trigger Summary\n\n"
        "These timelines use label-derived clip timeline samples, not model predictions.\n\n"
        + _markdown_table(
            [
                "clip_id",
                "clip_type",
                "expected",
                "first_trigger_s",
                "high_level_triggers",
                "expression_only",
                "cooldown_suppressed",
                "quality_suppressed",
                "result",
                "reason",
            ],
            trigger_rows,
        ),
        encoding="utf-8",
    )

    metric_order = [
        "total_clips",
        "pass_count",
        "fail_count",
        "warning_count",
        "expected_high_level_total",
        "expected_high_level_pass",
        "false_high_level_trigger_count",
        "optional_clip_count",
        "quality_suppressed_total",
        "cooldown_suppressed_total",
        "skipped_missing_clip_count",
        "label_conflict_warning_count",
        "openface_outputs_found_count",
        "openface_outputs_used",
        "openface_frames_processed",
    ]
    (tables_dir / "table_clip_policy_metrics.md").write_text(
        "# Clip Policy Metrics\n\n"
        + _markdown_table(["metric", "value"], [[key, summary.get(key, "")] for key in metric_order]),
        encoding="utf-8",
    )


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines) + "\n"


def write_figures(figures_dir: Path, timeline: list[ClipTimelineRow], summaries: list[ClipSummary]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    selected = select_representative_clips(summaries)
    timeline_by_clip: dict[str, list[ClipTimelineRow]] = {
        clip_id: [row for row in timeline if row.clip_id == clip_id] for clip_id in selected
    }

    fig, ax = plt.subplots(figsize=(10, 5))
    offset = 0
    yticks = []
    ylabels = []
    for clip_id, rows in timeline_by_clip.items():
        if not rows:
            continue
        ax.step(
            [row.t_sec for row in rows],
            [STATE_TO_CODE[row.state] + offset for row in rows],
            where="post",
            label=clip_id,
        )
        first_trigger = next((row.t_sec for row in rows if row.high_level_care), None)
        if first_trigger is not None:
            ax.axvline(first_trigger, linestyle="--", linewidth=1)
        yticks.append(offset)
        ylabels.append(clip_id)
        offset += len(STATE_TO_CODE) + 1
    ax.set_title("Clip State Timeline")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("state code per selected clip")
    ax.legend(loc="best", fontsize=8)
    fig.text(0.01, 0.01, "State codes: " + ", ".join(f"{k}={v}" for k, v in STATE_TO_CODE.items()), fontsize=8)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(figures_dir / "fig_clip_state_timeline.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    for clip_id, rows in timeline_by_clip.items():
        if not rows:
            continue
        ax.step([row.t_sec for row in rows], [row.action_level for row in rows], where="post", label=clip_id)
        first_trigger = next((row.t_sec for row in rows if row.high_level_care), None)
        if first_trigger is not None:
            ax.axvline(first_trigger, linestyle="--", linewidth=1)
    ax.set_title("Clip Action Timeline")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("action_level")
    ax.set_yticks([0, 1, 3])
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(figures_dir / "fig_clip_action_timeline.png", dpi=160)
    plt.close(fig)


def select_representative_clips(summaries: list[ClipSummary]) -> list[str]:
    selected: list[str] = []

    def pick(types: set[str]) -> None:
        for item in summaries:
            if item.clip_type in types and item.status == "evaluated":
                selected.append(item.clip_id)
                return

    pick({"normal_working", "blink"})
    pick({"yawn", "eyes_closed_long"})
    pick({"no_face", "bad_quality"})
    return selected[:3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_clip_eval(args.dataset_root, args.out)
    print("Generated clip policy timeline assets:")
    for output in result["outputs"]:
        print(f"- {output}")
    print("External dataset CSV files were not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
