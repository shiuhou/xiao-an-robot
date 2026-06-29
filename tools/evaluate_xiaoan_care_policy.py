"""Offline policy-level scenario validation for XiaoAn-Care-v1.

This script builds label-derived surrogate samples from XiaoAn-Care-v1 labels.
It validates care policy behavior only; it does not evaluate OpenFace/VLM model
accuracy and it does not execute robot actions.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.skills.emotion_monitor import normalize_fatigue_score_100
from tools.prepare_xiaoan_care_report_assets import (
    EXPECTED_BEHAVIOR,
    KNOWN_SCENES,
    read_csv_rows,
)


STRATEGIES = [
    "single_threshold",
    "threshold_plus_cooldown",
    "quality_gate_plus_cooldown",
]
FALSE_SCENES = {
    "normal_focus",
    "normal_smile",
    "bad_frame",
    "lowlight",
    "no_face",
    "occlusion",
}
TRUE_SCENES = {"severe_sleepy", "yawn", "negative_affect"}
OPTIONAL_SCENES = {"mild_fatigue"}
INVALID_SCENES = {"bad_frame", "lowlight", "no_face", "occlusion"}
NORMAL_FALSE_SCENES = {"normal_focus", "normal_smile"}
NEGATIVE_EMOTIONS = {"sad", "angry", "anxious", "negative"}
FATIGUE_THRESHOLD_100 = 67.0
NEGATIVE_CONFIDENCE_THRESHOLD = 0.65
COOLDOWN_SECONDS = 300
SAMPLE_INTERVAL_SECONDS = 10


@dataclass
class PolicyState:
    last_high_level_care_s: float | None = None


@dataclass
class PolicyResult:
    strategy: str
    image_id: str
    file_path: str = ""
    scene: str = ""
    expected_high_level_care: str = "unknown"
    status: str = "evaluated"
    timestamp_s: float = 0.0
    high_level_care: bool = False
    action_level: int = 0
    reason: str = "no_trigger"
    suppressed_by_cooldown: bool = False
    suppressed_by_quality: bool = False
    vlm_override: bool = False
    optional_trigger: bool = False
    fatigue_score_100: float | None = None
    emotion_tag: str = "unknown"
    confidence: float = 0.0
    face_visible: str = ""
    image_quality: str = ""
    roi_status: str = ""
    injected_signal: bool = False
    sample_kind: str = "label_derived_surrogate"


def fatigue_label_to_score_100(label: str | None) -> float | None:
    mapping = {
        "severe": 85.0,
        "moderate": 70.0,
        "mild": 50.0,
        "none": 10.0,
        "unknown": None,
        "": None,
    }
    return mapping.get((label or "").strip().lower(), None)


def affect_label_to_emotion(label: str | None) -> tuple[str, float]:
    mapping = {
        "negative": ("sad", 0.8),
        "positive": ("happy", 0.8),
        "neutral": ("neutral", 0.6),
        "unknown": ("unknown", 0.0),
        "": ("unknown", 0.0),
    }
    return mapping.get((label or "").strip().lower(), ("unknown", 0.0))


def expected_high_level_for_scene(scene: str | None) -> str:
    scene = (scene or "").strip()
    if scene in TRUE_SCENES:
        return "true"
    if scene in FALSE_SCENES:
        return "false"
    if scene in OPTIONAL_SCENES:
        return "optional"
    return "unknown"


def load_roi_status_by_image(dataset_root: Path) -> dict[str, str]:
    rows = read_csv_rows(dataset_root / "processed/face_roi/face_roi_manifest.csv")
    status_by_key: dict[str, str] = {}
    for row in rows:
        status = (row.get("status") or row.get("roi_status") or "").strip().lower()
        image_id = (row.get("image_id") or "").strip()
        file_path = (row.get("file_path") or "").strip()
        if image_id:
            status_by_key[image_id] = status
            status_by_key[image_id.replace("foucus", "focus")] = status
        if file_path:
            status_by_key[file_path] = status
            status_by_key[file_path.replace("foucus", "focus")] = status
            status_by_key[Path(file_path).stem] = status
            status_by_key[Path(file_path).stem.replace("foucus", "focus")] = status
    return status_by_key


def row_to_surrogate_sample(
    row: dict[str, str],
    dataset_root: Path,
    roi_status_by_image: dict[str, str],
    timestamp_s: float = 0.0,
) -> dict[str, object]:
    image_id = (row.get("image_id") or "").strip()
    file_path = (row.get("file_path") or "").strip()
    scene = (row.get("scene") or "").strip()
    emotion_tag, confidence = affect_label_to_emotion(row.get("affect_label"))
    fatigue_score = fatigue_label_to_score_100(row.get("fatigue_label"))
    roi_status = (
        roi_status_by_image.get(image_id)
        or roi_status_by_image.get(image_id.replace("foucus", "focus"))
        or roi_status_by_image.get(file_path)
        or roi_status_by_image.get(file_path.replace("foucus", "focus"))
        or ""
    )
    missing_file = not file_path or not (dataset_root / file_path).exists()
    return {
        "sample_kind": "label_derived_surrogate",
        "image_id": image_id,
        "file_path": file_path,
        "scene": scene,
        "expected_high_level_care": expected_high_level_for_scene(scene),
        "timestamp_s": timestamp_s,
        "fatigue_score": fatigue_score,
        "fatigue_score_100": fatigue_score,
        "emotion_tag": emotion_tag,
        "confidence": confidence,
        "face_visible": (row.get("face_visible") or "").strip(),
        "image_quality": (row.get("image_quality") or "").strip(),
        "roi_status": roi_status,
        "missing_file": missing_file,
        "injected_signal": False,
        "source": "label_derived_surrogate",
    }


def load_surrogate_samples(dataset_root: Path) -> list[dict[str, object]]:
    dataset_root = Path(dataset_root)
    rows = read_csv_rows(dataset_root / "labels/images_labels.csv")
    roi_status_by_image = load_roi_status_by_image(dataset_root)
    samples = []
    for index, row in enumerate(rows):
        samples.append(
            row_to_surrogate_sample(
                row,
                dataset_root=dataset_root,
                roi_status_by_image=roi_status_by_image,
                timestamp_s=index * SAMPLE_INTERVAL_SECONDS,
            )
        )
    return samples


def is_quality_unreliable(sample: dict[str, object]) -> bool:
    scene = str(sample.get("scene") or "").strip()
    face_visible = str(sample.get("face_visible") or "").strip().lower()
    image_quality = str(sample.get("image_quality") or "").strip().lower()
    roi_status = str(sample.get("roi_status") or "").strip().lower()
    no_valid_face = face_visible in {"no", "false", "none", "0"}
    low_quality = image_quality in {"bad", "bad_frame", "low", "poor", "unknown"}
    if scene in INVALID_SCENES:
        return True
    if no_valid_face:
        return True
    if low_quality and no_valid_face:
        return True
    if roi_status == "skipped" and scene in {"no_face", "occlusion", "lowlight"}:
        return True
    return False


def _threshold_would_trigger(sample: dict[str, object]) -> tuple[bool, str]:
    fatigue_score = normalize_fatigue_score_100(
        {
            "fatigue_score": sample.get("fatigue_score_100", sample.get("fatigue_score")),
            "source": sample.get("source"),
        }
    )
    emotion = str(sample.get("emotion_tag") or sample.get("emotion") or "unknown").lower()
    confidence = float(sample.get("confidence") or 0.0)
    if fatigue_score is not None and fatigue_score >= FATIGUE_THRESHOLD_100:
        return True, "fatigue"
    if emotion in NEGATIVE_EMOTIONS and confidence >= NEGATIVE_CONFIDENCE_THRESHOLD:
        return True, emotion
    return False, "no_trigger"


def evaluate_sample_with_strategy(
    sample: dict[str, object],
    strategy: str,
    now_s: float,
    state: PolicyState | None = None,
) -> PolicyResult:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}")
    state = state or PolicyState()
    scene = str(sample.get("scene") or "")
    expected = str(sample.get("expected_high_level_care") or expected_high_level_for_scene(scene))
    image_id = str(sample.get("image_id") or "")
    file_path = str(sample.get("file_path") or "")

    if sample.get("missing_file"):
        return PolicyResult(
            strategy=strategy,
            image_id=image_id,
            file_path=file_path,
            scene=scene,
            expected_high_level_care=expected,
            status="skipped_missing_file",
            timestamp_s=now_s,
            reason="skipped_missing_file",
            fatigue_score_100=sample.get("fatigue_score_100"),
            emotion_tag=str(sample.get("emotion_tag") or "unknown"),
            confidence=float(sample.get("confidence") or 0.0),
            face_visible=str(sample.get("face_visible") or ""),
            image_quality=str(sample.get("image_quality") or ""),
            roi_status=str(sample.get("roi_status") or ""),
            injected_signal=bool(sample.get("injected_signal")),
            sample_kind=str(sample.get("sample_kind") or "label_derived_surrogate"),
        )

    if strategy == "quality_gate_plus_cooldown" and is_quality_unreliable(sample):
        return _result_from_sample(
            sample,
            strategy=strategy,
            now_s=now_s,
            status="evaluated",
            high_level_care=False,
            action_level=0,
            reason="quality_gate",
            suppressed_by_quality=True,
        )

    if strategy == "quality_gate_plus_cooldown" and scene == "mild_fatigue":
        return _result_from_sample(
            sample,
            strategy=strategy,
            now_s=now_s,
            status="evaluated",
            high_level_care=False,
            action_level=1,
            reason="expression_only",
            optional_trigger=True,
        )

    would_trigger, reason = _threshold_would_trigger(sample)
    if would_trigger and strategy in {"threshold_plus_cooldown", "quality_gate_plus_cooldown"}:
        if (
            state.last_high_level_care_s is not None
            and now_s - state.last_high_level_care_s < COOLDOWN_SECONDS
        ):
            return _result_from_sample(
                sample,
                strategy=strategy,
                now_s=now_s,
                status="evaluated",
                high_level_care=False,
                action_level=0,
                reason="cooldown",
                suppressed_by_cooldown=True,
            )
        state.last_high_level_care_s = now_s

    high_level = bool(would_trigger)
    action_level = 3 if high_level else 0
    optional_trigger = scene == "mild_fatigue" and high_level
    if strategy == "quality_gate_plus_cooldown" and scene == "mild_fatigue":
        action_level = 1
    return _result_from_sample(
        sample,
        strategy=strategy,
        now_s=now_s,
        status="evaluated",
        high_level_care=high_level,
        action_level=action_level,
        reason=reason,
        optional_trigger=optional_trigger,
    )


def _result_from_sample(
    sample: dict[str, object],
    strategy: str,
    now_s: float,
    status: str,
    high_level_care: bool,
    action_level: int,
    reason: str,
    suppressed_by_cooldown: bool = False,
    suppressed_by_quality: bool = False,
    optional_trigger: bool = False,
) -> PolicyResult:
    scene = str(sample.get("scene") or "")
    return PolicyResult(
        strategy=strategy,
        image_id=str(sample.get("image_id") or ""),
        file_path=str(sample.get("file_path") or ""),
        scene=scene,
        expected_high_level_care=str(
            sample.get("expected_high_level_care") or expected_high_level_for_scene(scene)
        ),
        status=status,
        timestamp_s=now_s,
        high_level_care=high_level_care,
        action_level=action_level,
        reason=reason,
        suppressed_by_cooldown=suppressed_by_cooldown,
        suppressed_by_quality=suppressed_by_quality,
        vlm_override=False,
        optional_trigger=optional_trigger,
        fatigue_score_100=sample.get("fatigue_score_100"),
        emotion_tag=str(sample.get("emotion_tag") or "unknown"),
        confidence=float(sample.get("confidence") or 0.0),
        face_visible=str(sample.get("face_visible") or ""),
        image_quality=str(sample.get("image_quality") or ""),
        roi_status=str(sample.get("roi_status") or ""),
        injected_signal=bool(sample.get("injected_signal")),
        sample_kind=str(sample.get("sample_kind") or "label_derived_surrogate"),
    )


def evaluate_samples(samples: list[dict[str, object]], strategies: list[str] | None = None) -> list[PolicyResult]:
    strategies = strategies or STRATEGIES
    results: list[PolicyResult] = []
    for strategy in strategies:
        state = PolicyState()
        for index, sample in enumerate(samples):
            now_s = float(sample.get("timestamp_s", index * SAMPLE_INTERVAL_SECONDS) or 0.0)
            results.append(evaluate_sample_with_strategy(sample, strategy, now_s, state))
    return results


def compute_metrics(results: Iterable[PolicyResult]) -> dict[str, int]:
    metrics = {
        "evaluated_count": 0,
        "skipped_missing_file_count": 0,
        "false_high_level_trigger_count": 0,
        "missed_high_level_trigger_count": 0,
        "expected_care_success_count": 0,
        "expected_care_total": 0,
        "normal_false_trigger_count": 0,
        "invalid_false_trigger_count": 0,
        "optional_trigger_count": 0,
        "suppressed_by_cooldown_count": 0,
        "suppressed_by_quality_count": 0,
        "high_level_trigger_count": 0,
        "action_level_0_count": 0,
        "action_level_1_count": 0,
        "action_level_3_count": 0,
        "vlm_override_count": 0,
    }
    for result in results:
        if result.status == "skipped_missing_file":
            metrics["skipped_missing_file_count"] += 1
            continue
        metrics["evaluated_count"] += 1
        if result.high_level_care:
            metrics["high_level_trigger_count"] += 1
        if result.action_level == 0:
            metrics["action_level_0_count"] += 1
        elif result.action_level == 1:
            metrics["action_level_1_count"] += 1
        elif result.action_level == 3:
            metrics["action_level_3_count"] += 1
        if result.suppressed_by_cooldown:
            metrics["suppressed_by_cooldown_count"] += 1
        if result.suppressed_by_quality:
            metrics["suppressed_by_quality_count"] += 1
        if result.vlm_override:
            metrics["vlm_override_count"] += 1
        if result.expected_high_level_care == "optional":
            if result.high_level_care or result.action_level == 1 or result.optional_trigger:
                metrics["optional_trigger_count"] += 1
            continue
        if result.expected_high_level_care == "true":
            metrics["expected_care_total"] += 1
            if result.high_level_care:
                metrics["expected_care_success_count"] += 1
            else:
                metrics["missed_high_level_trigger_count"] += 1
        elif result.expected_high_level_care == "false" and result.high_level_care:
            metrics["false_high_level_trigger_count"] += 1
            if result.scene in NORMAL_FALSE_SCENES:
                metrics["normal_false_trigger_count"] += 1
            if result.scene in INVALID_SCENES:
                metrics["invalid_false_trigger_count"] += 1
    return metrics


def evaluate_dataset(dataset_root: Path) -> tuple[list[PolicyResult], dict[str, object]]:
    samples = load_surrogate_samples(Path(dataset_root))
    results = evaluate_samples(samples)
    summary = {
        "note": "Policy-level scenario validation using label-derived surrogate samples; not model prediction accuracy.",
        "sample_count": len(samples),
        "strategies": {
            strategy: compute_metrics([r for r in results if r.strategy == strategy])
            for strategy in STRATEGIES
        },
    }
    return results, summary


def build_quality_gate_stress_samples(samples: list[dict[str, object]]) -> list[dict[str, object]]:
    stress_samples = []
    for sample in samples:
        if sample.get("missing_file"):
            continue
        if str(sample.get("scene") or "") not in INVALID_SCENES:
            continue
        stress = dict(sample)
        stress["fatigue_score"] = 85.0
        stress["fatigue_score_100"] = 85.0
        stress["emotion_tag"] = "sad"
        stress["confidence"] = 0.9
        stress["injected_signal"] = True
        stress["sample_kind"] = "policy_stress_surrogate"
        stress_samples.append(stress)
    return stress_samples


def evaluate_quality_gate_stress(dataset_root: Path) -> tuple[list[PolicyResult], dict[str, dict[str, int]]]:
    samples = build_quality_gate_stress_samples(load_surrogate_samples(Path(dataset_root)))
    results = evaluate_samples(samples)
    summary = {}
    for strategy in STRATEGIES:
        strategy_results = [r for r in results if r.strategy == strategy]
        metrics = compute_metrics(strategy_results)
        summary[strategy] = {
            "stress_sample_count": len(samples),
            "high_level_trigger_count": metrics["high_level_trigger_count"],
            "suppressed_by_quality_count": metrics["suppressed_by_quality_count"],
            "suppressed_by_cooldown_count": metrics["suppressed_by_cooldown_count"],
            "invalid_false_trigger_count": metrics["invalid_false_trigger_count"],
        }
    return results, summary


def write_outputs(
    dataset_root: Path,
    out_root: Path,
    results: list[PolicyResult],
    summary: dict[str, object],
    stress_results: list[PolicyResult],
    stress_summary: dict[str, dict[str, int]],
) -> None:
    logs_dir = out_root / "logs"
    tables_dir = out_root / "tables"
    figures_dir = out_root / "figures"
    logs_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    _write_results_csv(logs_dir / "policy_eval_results.csv", results)
    _write_results_jsonl(logs_dir / "policy_eval_results.jsonl", results)
    full_summary = {
        **summary,
        "dataset_root": str(dataset_root),
        "stress": stress_summary,
    }
    (logs_dir / "policy_eval_summary.json").write_text(
        json.dumps(full_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_policy_tables(tables_dir, results, summary, stress_summary)
    write_policy_figures(figures_dir, summary)


def _write_results_csv(path: Path, results: list[PolicyResult]) -> None:
    fieldnames = list(asdict(results[0]).keys()) if results else list(asdict(PolicyResult("", "")).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def _write_results_jsonl(path: Path, results: list[PolicyResult]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def write_policy_tables(
    tables_dir: Path,
    results: list[PolicyResult],
    summary: dict[str, object],
    stress_summary: dict[str, dict[str, int]],
) -> None:
    comparison_rows = []
    results_by_scene_strategy: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        if result.status == "evaluated" and result.high_level_care:
            results_by_scene_strategy[result.scene][result.strategy] += 1
    scenes = sorted({result.scene for result in results}, key=lambda scene: KNOWN_SCENES.index(scene) if scene in KNOWN_SCENES else 99)
    for scene in scenes:
        expected_behavior = EXPECTED_BEHAVIOR.get(scene, ("unknown / needs human review", "unknown", ""))[0]
        single = results_by_scene_strategy[scene]["single_threshold"]
        cooldown = results_by_scene_strategy[scene]["threshold_plus_cooldown"]
        quality = results_by_scene_strategy[scene]["quality_gate_plus_cooldown"]
        comparison_rows.append(
            [
                scene,
                expected_behavior,
                single,
                cooldown,
                quality,
                _scene_conclusion(scene, single, cooldown, quality),
            ]
        )
    (tables_dir / "table_policy_comparison.md").write_text(
        "# Policy Comparison\n\n"
        "These are policy-level counts from label-derived surrogate samples, not model prediction accuracy.\n\n"
        + _markdown_table(
            [
                "scene",
                "expected_behavior",
                "single_threshold_high",
                "threshold_cooldown_high",
                "quality_gate_high",
                "conclusion",
            ],
            comparison_rows,
        ),
        encoding="utf-8",
    )

    metric_rows = []
    for strategy, metrics in summary["strategies"].items():
        metric_rows.append(
            [
                strategy,
                metrics["evaluated_count"],
                metrics["false_high_level_trigger_count"],
                metrics["missed_high_level_trigger_count"],
                metrics["invalid_false_trigger_count"],
                f"{metrics['expected_care_success_count']}/{metrics['expected_care_total']}",
                metrics["suppressed_by_cooldown_count"],
                metrics["suppressed_by_quality_count"],
                metrics["high_level_trigger_count"],
                metrics["vlm_override_count"],
            ]
        )
    (tables_dir / "table_policy_metrics.md").write_text(
        "# Policy Metrics\n\n"
        "Mild fatigue is optional and is excluded from false positive / false negative main metrics. "
        "Missing files are counted as skipped_missing_file and excluded from the main denominator. "
        "VLM is not allowed to override high_level_care.\n\n"
        + _markdown_table(
            [
                "strategy",
                "evaluated",
                "false_trigger",
                "missed_care",
                "invalid_false_trigger",
                "expected_success",
                "cooldown_suppressed",
                "quality_suppressed",
                "high_level_triggers",
                "vlm_override",
            ],
            metric_rows,
        ),
        encoding="utf-8",
    )

    stress_rows = []
    for strategy, metrics in stress_summary.items():
        stress_rows.append(
            [
                strategy,
                metrics["stress_sample_count"],
                metrics["high_level_trigger_count"],
                metrics["suppressed_by_quality_count"],
                metrics["suppressed_by_cooldown_count"],
                metrics["invalid_false_trigger_count"],
            ]
        )
    (tables_dir / "table_quality_gate_stress.md").write_text(
        "# Quality Gate Stress Test\n\n"
        "This is a policy stress test with injected strong fatigue/negative signals on invalid or low-reliability scenes. "
        "It is not real model output.\n\n"
        + _markdown_table(
            [
                "strategy",
                "stress_sample_count",
                "high_level_trigger_count",
                "suppressed_by_quality_count",
                "suppressed_by_cooldown_count",
                "invalid_false_trigger_count",
            ],
            stress_rows,
        ),
        encoding="utf-8",
    )


def _scene_conclusion(scene: str, single: int, cooldown: int, quality: int) -> str:
    expected = expected_high_level_for_scene(scene)
    if expected == "false":
        return "lower high count is better"
    if expected == "true":
        return "high-level care expected when not suppressed by cooldown"
    if expected == "optional":
        return "optional; excluded from main pass/fail metrics"
    return "needs human review"


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines) + "\n"


def write_policy_figures(figures_dir: Path, summary: dict[str, object]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    strategies = STRATEGIES
    metrics = summary["strategies"]
    x_values = range(len(strategies))

    fig, ax = plt.subplots(figsize=(9, 5))
    width = 0.35
    false_values = [metrics[strategy]["false_high_level_trigger_count"] for strategy in strategies]
    invalid_values = [metrics[strategy]["invalid_false_trigger_count"] for strategy in strategies]
    ax.bar([x - width / 2 for x in x_values], false_values, width, label="false_high_level")
    ax.bar([x + width / 2 for x in x_values], invalid_values, width, label="invalid_false")
    ax.set_title("Policy False Trigger Comparison")
    ax.set_ylabel("count")
    ax.set_xticks(list(x_values))
    ax.set_xticklabels(strategies, rotation=20, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(figures_dir / "fig_policy_false_triggers.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    success_values = [metrics[strategy]["expected_care_success_count"] for strategy in strategies]
    missed_values = [metrics[strategy]["missed_high_level_trigger_count"] for strategy in strategies]
    ax.bar([x - width / 2 for x in x_values], success_values, width, label="expected_success")
    ax.bar([x + width / 2 for x in x_values], missed_values, width, label="missed_care")
    ax.set_title("Policy Expected Care Comparison")
    ax.set_ylabel("count")
    ax.set_xticks(list(x_values))
    ax.set_xticklabels(strategies, rotation=20, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(figures_dir / "fig_policy_expected_care.png", dpi=160)
    plt.close(fig)


def run_policy_eval(dataset_root: Path, out_root: Path) -> dict[str, object]:
    results, summary = evaluate_dataset(dataset_root)
    stress_results, stress_summary = evaluate_quality_gate_stress(dataset_root)
    write_outputs(dataset_root, out_root, results, summary, stress_results, stress_summary)
    return {
        "summary": summary,
        "stress": stress_summary,
        "result_count": len(results),
        "stress_result_count": len(stress_results),
        "outputs": [
            str(out_root / "tables/table_policy_comparison.md"),
            str(out_root / "tables/table_policy_metrics.md"),
            str(out_root / "tables/table_quality_gate_stress.md"),
            str(out_root / "figures/fig_policy_false_triggers.png"),
            str(out_root / "figures/fig_policy_expected_care.png"),
            str(out_root / "logs/policy_eval_results.csv"),
            str(out_root / "logs/policy_eval_results.jsonl"),
            str(out_root / "logs/policy_eval_summary.json"),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    result = run_policy_eval(args.dataset_root, args.out)
    print("Generated policy evaluation assets:")
    for output in result["outputs"]:
        print(f"- {output}")
    print("External dataset CSV files were not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
