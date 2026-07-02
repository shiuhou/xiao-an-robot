"""Prepare report-ready tables, figures, and issue logs for XiaoAn-Care-v1."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


KNOWN_SCENES = [
    "normal_focus",
    "normal_smile",
    "bad_frame",
    "lowlight",
    "no_face",
    "occlusion",
    "mild_fatigue",
    "severe_sleepy",
    "yawn",
    "negative_affect",
]

EXPECTED_BEHAVIOR = {
    "normal_focus": (
        "observe only, no interruption",
        "false",
        "normal focused state",
    ),
    "normal_smile": (
        "observe only, no interruption",
        "false",
        "positive/normal state",
    ),
    "bad_frame": (
        "reject or observe due to poor frame quality",
        "false",
        "unreliable visual evidence",
    ),
    "lowlight": (
        "reject or low-confidence observe",
        "false",
        "insufficient lighting",
    ),
    "no_face": (
        "no face, no care decision",
        "false",
        "no valid human face",
    ),
    "occlusion": (
        "no high-level care",
        "false",
        "face is occluded",
    ),
    "mild_fatigue": (
        "light hint or expression only",
        "optional",
        "weak fatigue evidence",
    ),
    "severe_sleepy": (
        "care reminder expected",
        "true",
        "strong fatigue evidence",
    ),
    "yawn": (
        "fatigue reminder expected",
        "true",
        "yawn evidence",
    ),
    "negative_affect": (
        "gentle care expected",
        "true",
        "negative affect evidence",
    ),
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return [dict(row) for row in csv.DictReader(f)]


def read_csv_columns(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or [])


def _write_csv_rows(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _distribution(rows: Iterable[dict[str, str]], field: str) -> dict[str, int]:
    counts = Counter((row.get(field) or "<empty>").strip() or "<empty>" for row in rows)
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _binary_distribution(rows: Iterable[dict[str, str]], field: str) -> dict[str, int]:
    counts = _distribution(rows, field)
    for key in ("0", "1"):
        counts.setdefault(key, 0)
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _relative_exists(dataset_root: Path, value: str | None) -> bool:
    if not value or _is_not_applicable_path(value):
        return False
    return (dataset_root / value).exists()


def _is_not_applicable_path(value: str | None) -> bool:
    return (value or "").strip().lower() in {"", "n/a", "na", "none", "not_applicable"}


def _basename_stem(value: str | None) -> str:
    if not value:
        return ""
    return Path(value).stem


def _manifest_status(row: dict[str, str]) -> str:
    return (row.get("status") or row.get("roi_status") or "").strip().lower()


def _infer_scene_from_identifier(identifier: str) -> str:
    identifier = identifier.replace("foucus", "focus")
    for scene in sorted(KNOWN_SCENES, key=len, reverse=True):
        if scene in identifier:
            return scene
    return "unknown"


def _scene_for_row(
    row: dict[str, str],
    image_scene_by_id: dict[str, str],
) -> str:
    scene = (row.get("scene") or "").strip()
    if scene:
        return scene
    image_id = (row.get("image_id") or "").strip()
    if image_id in image_scene_by_id:
        return image_scene_by_id[image_id]
    return _infer_scene_from_identifier(" ".join([image_id, row.get("file_path") or ""]))


def _compact_distribution(values: dict[str, int]) -> str:
    if not values:
        return "-"
    return ", ".join(f"{key}: {value}" for key, value in values.items())


def _issue(
    severity: str,
    code: str,
    file: str,
    row: int | None,
    field: str,
    value: str,
    message: str,
) -> dict[str, object]:
    return {
        "severity": severity,
        "code": code,
        "file": file,
        "row": row,
        "field": field,
        "value": value,
        "message": message,
    }


def _load_dataset_rows(dataset_root: Path) -> dict[str, list[dict[str, str]]]:
    return {
        "images": read_csv_rows(dataset_root / "labels/images_labels.csv"),
        "clips": read_csv_rows(dataset_root / "labels/clips_labels.csv"),
        "vlm": read_csv_rows(dataset_root / "labels/vlm_eval_labels.csv"),
        "roi": read_csv_rows(dataset_root / "processed/face_roi/face_roi_manifest.csv"),
    }


def _load_dataset_columns(dataset_root: Path) -> dict[str, list[str]]:
    return {
        "images": read_csv_columns(dataset_root / "labels/images_labels.csv"),
        "clips": read_csv_columns(dataset_root / "labels/clips_labels.csv"),
        "vlm": read_csv_columns(dataset_root / "labels/vlm_eval_labels.csv"),
        "roi": read_csv_columns(dataset_root / "processed/face_roi/face_roi_manifest.csv"),
    }


def build_dataset_summary(dataset_root: Path) -> dict[str, object]:
    dataset_root = Path(dataset_root)
    rows = _load_dataset_rows(dataset_root)
    columns = _load_dataset_columns(dataset_root)
    image_scene_by_id = {
        (row.get("image_id") or "").strip(): (row.get("scene") or "").strip()
        for row in rows["images"]
        if (row.get("image_id") or "").strip()
    }

    roi_status_by_scene: dict[str, Counter[str]] = defaultdict(Counter)
    roi_overall = Counter()
    for row in rows["roi"]:
        status = _manifest_status(row) or "<empty>"
        scene = _scene_for_row(row, image_scene_by_id)
        roi_overall[status] += 1
        roi_status_by_scene[scene][status] += 1

    roi_status_by_scene_out = {
        scene: dict(sorted(counts.items(), key=lambda item: item[0]))
        for scene, counts in sorted(roi_status_by_scene.items(), key=lambda item: item[0])
    }
    for counts in roi_status_by_scene_out.values():
        counts.setdefault("ok", 0)
        counts.setdefault("skipped", 0)

    vlm_scene_counts = Counter()
    for row in rows["vlm"]:
        vlm_scene_counts[_scene_for_row(row, image_scene_by_id)] += 1

    clip_details = [
        {
            "clip_id": row.get("clip_id", ""),
            "duration_sec": row.get("duration_sec", ""),
            "scene": row.get("scene", ""),
            "care_needed": row.get("care_needed", ""),
            "start_time_sec": row.get("start_time_sec", ""),
            "end_time_sec": row.get("end_time_sec", ""),
        }
        for row in rows["clips"]
    ]

    return {
        "dataset_root": str(dataset_root),
        "totals": {
            "static_images": len(rows["images"]),
            "clips": len(rows["clips"]),
            "vlm_eval": len(rows["vlm"]),
            "roi_manifest": len(rows["roi"]),
        },
        "columns": columns,
        "images": {
            "scene_distribution": _distribution(rows["images"], "scene"),
            "care_needed_distribution": _binary_distribution(rows["images"], "care_needed"),
            "fatigue_label_distribution": _distribution(rows["images"], "fatigue_label"),
            "affect_label_distribution": _distribution(rows["images"], "affect_label"),
        },
        "clips": {
            "care_needed_distribution": _binary_distribution(rows["clips"], "care_needed"),
            "details": clip_details,
        },
        "vlm": {
            "expected_care_needed_distribution": _binary_distribution(
                rows["vlm"], "expected_care_needed"
            ),
            "scene_distribution": dict(sorted(vlm_scene_counts.items())),
        },
        "roi": {
            "overall_status": dict(sorted(roi_overall.items(), key=lambda item: item[0])),
            "status_by_scene": roi_status_by_scene_out,
        },
    }


def find_dataset_issues(dataset_root: Path) -> list[dict[str, object]]:
    dataset_root = Path(dataset_root)
    rows = _load_dataset_rows(dataset_root)
    issues: list[dict[str, object]] = []
    image_scene_by_id = {
        (row.get("image_id") or "").strip(): (row.get("scene") or "").strip()
        for row in rows["images"]
        if (row.get("image_id") or "").strip()
    }
    roi_status_by_id = {
        (row.get("image_id") or "").strip(): _manifest_status(row)
        for row in rows["roi"]
        if (row.get("image_id") or "").strip()
    }

    def check_required(row: dict[str, str], file_label: str, idx: int, fields: list[str]):
        for field in fields:
            value = (row.get(field) or "").strip()
            if not value:
                issues.append(
                    _issue(
                        "error",
                        "empty_required_field",
                        file_label,
                        idx,
                        field,
                        value,
                        f"{field} is empty.",
                    )
                )

    for idx, row in enumerate(rows["images"], start=2):
        check_required(row, "labels/images_labels.csv", idx, ["image_id", "file_path", "scene"])
        file_path = (row.get("file_path") or "").strip()
        image_id = (row.get("image_id") or "").strip()
        if file_path and not _relative_exists(dataset_root, file_path):
            issues.append(
                _issue(
                    "error",
                    "missing_file_path",
                    "labels/images_labels.csv",
                    idx,
                    "file_path",
                    file_path,
                    "Image file_path does not exist.",
                )
            )
        if image_id and file_path and image_id != _basename_stem(file_path):
            issues.append(
                _issue(
                    "warning",
                    "image_id_file_path_mismatch",
                    "labels/images_labels.csv",
                    idx,
                    "image_id/file_path",
                    f"{image_id} != {_basename_stem(file_path)}",
                    "image_id does not match file_path basename.",
                )
            )
        if (row.get("care_needed") or "").strip() not in {"0", "1"}:
            issues.append(
                _issue(
                    "error",
                    "invalid_care_needed",
                    "labels/images_labels.csv",
                    idx,
                    "care_needed",
                    row.get("care_needed") or "",
                    "care_needed must be 0 or 1.",
                )
            )
        _add_focus_foucus_issues(issues, row, "labels/images_labels.csv", idx)

    for idx, row in enumerate(rows["clips"], start=2):
        if (row.get("care_needed") or "").strip() not in {"0", "1"}:
            issues.append(
                _issue(
                    "error",
                    "invalid_care_needed",
                    "labels/clips_labels.csv",
                    idx,
                    "care_needed",
                    row.get("care_needed") or "",
                    "care_needed must be 0 or 1.",
                )
            )

    for idx, row in enumerate(rows["vlm"], start=2):
        check_required(row, "labels/vlm_eval_labels.csv", idx, ["image_id", "file_path"])
        file_path = (row.get("file_path") or "").strip()
        roi_path = (row.get("roi_path") or "").strip()
        image_id = (row.get("image_id") or "").strip()
        scene = _scene_for_row(row, image_scene_by_id)
        if file_path and not _relative_exists(dataset_root, file_path):
            issues.append(
                _issue(
                    "error",
                    "missing_file_path",
                    "labels/vlm_eval_labels.csv",
                    idx,
                    "file_path",
                    file_path,
                    "VLM eval file_path does not exist.",
                )
            )
        roi_not_applicable = scene == "no_face" and (
            _is_not_applicable_path(roi_path) or roi_status_by_id.get(image_id) == "skipped"
        )
        if roi_not_applicable:
            issues.append(
                _issue(
                    "info",
                    "roi_not_applicable",
                    "labels/vlm_eval_labels.csv",
                    idx,
                    "roi_path",
                    roi_path,
                    "ROI is not applicable for no_face eval rows.",
                )
            )
        elif not roi_path or not _relative_exists(dataset_root, roi_path):
            issues.append(
                _issue(
                    "error",
                    "missing_roi_path",
                    "labels/vlm_eval_labels.csv",
                    idx,
                    "roi_path",
                    roi_path,
                    "VLM eval roi_path does not exist.",
                )
            )
        if image_id and file_path and image_id != _basename_stem(file_path):
            issues.append(
                _issue(
                    "warning",
                    "image_id_file_path_mismatch",
                    "labels/vlm_eval_labels.csv",
                    idx,
                    "image_id/file_path",
                    f"{image_id} != {_basename_stem(file_path)}",
                    "image_id does not match file_path basename.",
                )
            )
        if image_id and roi_status_by_id.get(image_id) == "skipped" and not roi_not_applicable:
            issues.append(
                _issue(
                    "warning",
                    "vlm_eval_points_to_skipped_roi",
                    "labels/vlm_eval_labels.csv",
                    idx,
                    "image_id",
                    image_id,
                    "VLM eval image points to a skipped ROI manifest row.",
                )
            )
        if (row.get("expected_care_needed") or "").strip() not in {"0", "1"}:
            issues.append(
                _issue(
                    "error",
                    "invalid_expected_care_needed",
                    "labels/vlm_eval_labels.csv",
                    idx,
                    "expected_care_needed",
                    row.get("expected_care_needed") or "",
                    "expected_care_needed must be 0 or 1.",
                )
            )
        _add_focus_foucus_issues(issues, row, "labels/vlm_eval_labels.csv", idx)

    for idx, row in enumerate(rows["roi"], start=2):
        check_required(row, "processed/face_roi/face_roi_manifest.csv", idx, ["image_id"])
        file_path = (row.get("file_path") or "").strip()
        roi_path = (row.get("roi_path") or "").strip()
        status = _manifest_status(row)
        if file_path and not _relative_exists(dataset_root, file_path):
            issues.append(
                _issue(
                    "error",
                    "missing_file_path",
                    "processed/face_roi/face_roi_manifest.csv",
                    idx,
                    "file_path",
                    file_path,
                    "ROI manifest file_path does not exist.",
                )
            )
        if status == "ok" and (not roi_path or not _relative_exists(dataset_root, roi_path)):
            issues.append(
                _issue(
                    "error",
                    "missing_ok_roi_path",
                    "processed/face_roi/face_roi_manifest.csv",
                    idx,
                    "roi_path",
                    roi_path,
                    "ROI manifest status=ok but roi_path does not exist.",
                )
            )
        if status == "skipped" and (not roi_path or not _relative_exists(dataset_root, roi_path)):
            issues.append(
                _issue(
                    "warning",
                    "skipped_roi_missing_path",
                    "processed/face_roi/face_roi_manifest.csv",
                    idx,
                    "roi_path",
                    roi_path,
                    "ROI manifest status=skipped has no usable roi_path; this is expected for skipped rows.",
                )
            )
        _add_focus_foucus_issues(
            issues, row, "processed/face_roi/face_roi_manifest.csv", idx
        )

    unknown_scenes = sorted(
        {
            _scene_for_row(row, image_scene_by_id)
            for row in [*rows["images"], *rows["roi"], *rows["vlm"]]
            if _scene_for_row(row, image_scene_by_id) not in KNOWN_SCENES
        }
    )
    for scene in unknown_scenes:
        issues.append(
            _issue(
                "info",
                "unknown_scene_needs_review",
                "dataset",
                None,
                "scene",
                scene,
                "Scene is not in the expected behavior table and needs human review.",
            )
        )

    return issues


def _add_focus_foucus_issues(
    issues: list[dict[str, object]],
    row: dict[str, str],
    file_label: str,
    idx: int,
) -> None:
    values = [
        row.get("image_id") or "",
        row.get("file_path") or "",
        row.get("roi_path") or "",
    ]
    if any("foucus" in value for value in values):
        issues.append(
            _issue(
                "warning",
                "focus_foucus_inconsistency",
                file_label,
                idx,
                "image_id/file_path/roi_path",
                " | ".join(value for value in values if value),
                "Found foucus/focus naming inconsistency.",
            )
        )


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(value) for value in row) + " |")
    return "\n".join(lines) + "\n"


def _md_cell(value: object) -> str:
    text = str(value)
    return text.replace("\n", "<br>").replace("|", "\\|")


def write_markdown_tables(
    summary: dict[str, object],
    issues: list[dict[str, object]],
    out_root: Path,
) -> None:
    tables_dir = out_root / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    images = summary["images"]
    clips = summary["clips"]
    vlm = summary["vlm"]
    roi = summary["roi"]
    totals = summary["totals"]

    coverage_rows = [
        ["static_images", totals["static_images"]],
        ["clips", totals["clips"]],
        ["vlm_eval", totals["vlm_eval"]],
        ["roi_manifest", totals["roi_manifest"]],
        ["images_by_scene", _compact_distribution(images["scene_distribution"])],
        ["images_care_needed", _compact_distribution(images["care_needed_distribution"])],
        ["fatigue_label", _compact_distribution(images["fatigue_label_distribution"])],
        ["affect_label", _compact_distribution(images["affect_label_distribution"])],
        ["clips_care_needed", _compact_distribution(clips["care_needed_distribution"])],
        [
            "vlm_expected_care_needed",
            _compact_distribution(vlm["expected_care_needed_distribution"]),
        ],
    ]
    (tables_dir / "table_dataset_coverage.md").write_text(
        "# Dataset Coverage\n\n" + _markdown_table(["metric", "value"], coverage_rows),
        encoding="utf-8",
    )

    known_scenes = set(KNOWN_SCENES)
    csv_scenes = set(images["scene_distribution"].keys())
    behavior_rows = []
    for scene in KNOWN_SCENES:
        action, expected_trigger, rationale = EXPECTED_BEHAVIOR[scene]
        behavior_rows.append([scene, action, expected_trigger, rationale])
    for scene in sorted(csv_scenes - known_scenes):
        behavior_rows.append([scene, "unknown / needs human review", "unknown", "not in policy table"])
    (tables_dir / "table_expected_behavior.md").write_text(
        "# Expected Behavior\n\n"
        + _markdown_table(
            ["scene", "expected_behavior", "expected_trigger", "rationale"],
            behavior_rows,
        ),
        encoding="utf-8",
    )

    roi_rows = []
    for scene, counts in roi["status_by_scene"].items():
        ok = int(counts.get("ok", 0))
        skipped = int(counts.get("skipped", 0))
        total = sum(int(value) for value in counts.values())
        ok_rate = f"{ok / total:.2%}" if total else "0.00%"
        roi_rows.append([scene, total, ok, skipped, ok_rate])
    overall = roi["overall_status"]
    overall_ok = int(overall.get("ok", 0))
    overall_skipped = int(overall.get("skipped", 0))
    overall_total = sum(int(value) for value in overall.values())
    roi_rows.append(
        [
            "OVERALL",
            overall_total,
            overall_ok,
            overall_skipped,
            f"{overall_ok / overall_total:.2%}" if overall_total else "0.00%",
        ]
    )
    (tables_dir / "table_roi_status_by_scene.md").write_text(
        "# ROI Status By Scene\n\n"
        "ROI success means only that a candidate face area was produced; it is not an emotion judgment.\n\n"
        + _markdown_table(["scene", "total", "ok", "skipped", "ok_rate"], roi_rows),
        encoding="utf-8",
    )

    if issues:
        issue_rows = [
            [
                issue["severity"],
                issue["code"],
                issue["file"],
                issue.get("row") or "",
                issue["field"],
                issue["value"],
                issue["message"],
            ]
            for issue in issues
        ]
    else:
        issue_rows = [["info", "no_issues_found", "", "", "", "", "No issues found."]]
    (tables_dir / "table_dataset_issues.md").write_text(
        "# Dataset Issues\n\n"
        + _markdown_table(
            ["severity", "code", "file", "row", "field", "value", "message"],
            issue_rows,
        ),
        encoding="utf-8",
    )


def write_figures(summary: dict[str, object], out_root: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir = out_root / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    _bar_chart(
        plt,
        summary["images"]["scene_distribution"],
        "Image Scene Distribution",
        "scene",
        "count",
        figures_dir / "fig_scene_distribution.png",
        rotate=40,
    )
    _bar_chart(
        plt,
        summary["images"]["care_needed_distribution"],
        "Image Care Needed Distribution",
        "care_needed",
        "count",
        figures_dir / "fig_care_needed_distribution.png",
    )

    roi_by_scene = summary["roi"]["status_by_scene"]
    scenes = list(roi_by_scene.keys())
    ok_values = [int(roi_by_scene[scene].get("ok", 0)) for scene in scenes]
    skipped_values = [int(roi_by_scene[scene].get("skipped", 0)) for scene in scenes]
    fig, ax = plt.subplots(figsize=(10, 5))
    x_values = range(len(scenes))
    ax.bar(x_values, ok_values, label="ok")
    ax.bar(x_values, skipped_values, bottom=ok_values, label="skipped")
    ax.set_title("ROI Status By Scene")
    ax.set_xlabel("scene")
    ax.set_ylabel("count")
    ax.set_xticks(list(x_values))
    ax.set_xticklabels(scenes, rotation=40, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(figures_dir / "fig_roi_status_by_scene.png", dpi=160)
    plt.close(fig)


def _bar_chart(plt, values: dict[str, int], title: str, xlabel: str, ylabel: str, path: Path, rotate: int = 0):
    labels = list(values.keys())
    counts = list(values.values())
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, counts)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if rotate:
        ax.tick_params(axis="x", labelrotation=rotate)
        for label in ax.get_xticklabels():
            label.set_ha("right")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_json_logs(
    summary: dict[str, object],
    issues: list[dict[str, object]],
    out_root: Path,
) -> None:
    logs_dir = out_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (logs_dir / "dataset_issues.json").write_text(
        json.dumps({"issues": issues}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fix_obvious_focus_typos(dataset_root: Path) -> list[Path]:
    changed_files: list[Path] = []
    for rel_path in [
        Path("labels/images_labels.csv"),
        Path("labels/vlm_eval_labels.csv"),
    ]:
        csv_path = dataset_root / rel_path
        rows = read_csv_rows(csv_path)
        columns = read_csv_columns(csv_path)
        if not rows or not columns:
            continue
        changed = False
        for row in rows:
            value = row.get("file_path") or ""
            if "foucus" not in value:
                continue
            candidate = value.replace("foucus", "focus")
            if not _relative_exists(dataset_root, value) and _relative_exists(dataset_root, candidate):
                row["file_path"] = candidate
                changed = True
        if changed:
            backup_path = csv_path.with_suffix(csv_path.suffix + ".bak")
            if not backup_path.exists():
                shutil.copy2(csv_path, backup_path)
            _write_csv_rows(csv_path, columns, rows)
            changed_files.append(csv_path)
    return changed_files


def prepare_assets(
    dataset_root: Path,
    out_root: Path,
    fix_obvious_typos: bool = False,
) -> dict[str, object]:
    dataset_root = Path(dataset_root)
    out_root = Path(out_root)
    fixed_files: list[Path] = []
    if fix_obvious_typos:
        fixed_files = fix_obvious_focus_typos(dataset_root)
    summary = build_dataset_summary(dataset_root)
    issues = find_dataset_issues(dataset_root)
    write_markdown_tables(summary, issues, out_root)
    write_figures(summary, out_root)
    write_json_logs(summary, issues, out_root)
    return {
        "summary": summary,
        "issues": issues,
        "fixed_files": [str(path) for path in fixed_files],
        "outputs": [
            str(out_root / "tables/table_dataset_coverage.md"),
            str(out_root / "tables/table_expected_behavior.md"),
            str(out_root / "tables/table_roi_status_by_scene.md"),
            str(out_root / "tables/table_dataset_issues.md"),
            str(out_root / "figures/fig_scene_distribution.png"),
            str(out_root / "figures/fig_care_needed_distribution.png"),
            str(out_root / "figures/fig_roi_status_by_scene.png"),
            str(out_root / "logs/dataset_summary.json"),
            str(out_root / "logs/dataset_issues.json"),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fix-obvious-typos", action="store_true")
    args = parser.parse_args(argv)

    result = prepare_assets(
        dataset_root=args.dataset_root,
        out_root=args.out,
        fix_obvious_typos=args.fix_obvious_typos,
    )
    print("Generated report assets:")
    for output in result["outputs"]:
        print(f"- {output}")
    if result["fixed_files"]:
        print("Modified dataset CSV files:")
        for path in result["fixed_files"]:
            print(f"- {path}")
    else:
        print("External dataset CSV files were not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
