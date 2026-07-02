#!/usr/bin/env python
"""Evaluate VLM JSON behavior on the offline labeled image set."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


EVAL_ROOT = Path("manual_outputs") / "visual_eval" / "vlm_v0_1"
DEFAULT_ANNOTATIONS = EVAL_ROOT / "annotations" / "vlm_image_labels.csv"
DEFAULT_PROMPT = EVAL_ROOT / "prompts" / "vlm_prompt_v0_1.txt"
DEFAULT_OUTPUTS = EVAL_ROOT / "outputs" / "vlm_outputs.jsonl"
DEFAULT_REPORT = EVAL_ROOT / "reports" / "vlm_eval_summary.csv"
PROMPT_VERSION = "vlm_prompt_v0_1"

REQUIRED_FIELDS = (
    "executed",
    "status",
    "visible_state",
    "care_state",
    "confidence",
    "visible_evidence",
    "message",
)
VALID_STATUS = {"ok", "invalid_observation", "model_error"}
VALID_VISIBLE_STATES = {
    "neutral_visible",
    "positive_visible",
    "negative_visible",
    "fatigue_visible",
    "invalid_observation",
}
VALID_CARE_STATES = {"no_care", "needs_care", "uncertain"}
GLOBAL_FORBIDDEN_CLAIMS = {
    "fatigue_score",
    "fatigue_level",
    "ear",
    "perclos",
    "mar",
    "au",
    "observation_quality",
    "gate",
}
SUMMARY_COLUMNS = [
    "total_samples",
    "json_parse_success_rate",
    "required_fields_present_rate",
    "enum_valid_rate",
    "visible_state_accuracy",
    "care_state_accuracy",
    "neutral_false_care_rate",
    "invalid_observation_accuracy",
    "forbidden_claims_rate",
    "avg_latency_ms",
    "timeout_count",
    "model_error_count",
    "parse_error_count",
]


def ensure_repo_root_on_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return repo_root


@dataclass
class ParseResult:
    ok: bool
    value: dict[str, Any]
    error: str


@dataclass
class ValidationResult:
    required_fields_present: bool
    enum_valid: bool
    visible_state_match: bool
    care_state_match: bool
    forbidden_claims_hit: bool
    neutral_false_care: bool
    invalid_observation_match: bool | None


def _json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start:end + 1]
    return text


def parse_vlm_output(raw: str) -> ParseResult:
    try:
        value = json.loads(_json_text(raw))
    except json.JSONDecodeError as exc:
        return ParseResult(False, {}, f"json_parse_error: {exc.msg}")
    if not isinstance(value, dict):
        return ParseResult(False, {}, "json_parse_error: expected object")
    return ParseResult(True, value, "")


def _normalized_terms(text: str) -> list[str]:
    return [item.strip().lower() for item in text.split(";") if item.strip()]


def _contains_forbidden_claim(value: Any, terms: set[str]) -> bool:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    return any(
        term and re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text)
        for term in terms
    )


def validate_output(parsed: dict[str, Any], label: dict[str, str]) -> ValidationResult:
    required_present = all(field in parsed for field in REQUIRED_FIELDS)
    status = parsed.get("status")
    visible_state = parsed.get("visible_state")
    care_state = parsed.get("care_state")
    confidence = parsed.get("confidence")
    evidence = parsed.get("visible_evidence")
    message = parsed.get("message")
    enum_valid = (
        isinstance(parsed.get("executed"), bool)
        and status in VALID_STATUS
        and visible_state in VALID_VISIBLE_STATES
        and care_state in VALID_CARE_STATES
        and isinstance(confidence, (int, float))
        and 0.0 <= float(confidence) <= 1.0
        and isinstance(evidence, (list, str))
        and isinstance(message, str)
    )

    expected_visible = label.get("expected_visible_state", "")
    expected_care = label.get("expected_care_state", "")
    forbidden_terms = set(_normalized_terms(label.get("forbidden_claims", "")))
    forbidden_terms.update(GLOBAL_FORBIDDEN_CLAIMS)
    forbidden_hit = _contains_forbidden_claim(parsed, forbidden_terms)
    neutral_false_care = expected_care == "no_care" and care_state == "needs_care"
    invalid_match: bool | None = None
    if expected_visible == "invalid_observation":
        invalid_match = visible_state == "invalid_observation"

    return ValidationResult(
        required_fields_present=required_present,
        enum_valid=enum_valid,
        visible_state_match=visible_state == expected_visible,
        care_state_match=care_state == expected_care,
        forbidden_claims_hit=forbidden_hit,
        neutral_false_care=neutral_false_care,
        invalid_observation_match=invalid_match,
    )


def load_annotations(path: str | Path) -> list[dict[str, str]]:
    ann_path = Path(path)
    with ann_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"annotations file is empty: {ann_path}")
        required = {
            "sample_id",
            "image_path",
            "expected_visible_state",
            "expected_care_state",
            "forbidden_claims",
        }
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"annotations CSV missing columns: {sorted(missing)}")
        return [dict(row) for row in reader]


def filter_annotations(
    annotations: list[dict[str, str]],
    limit: int | None = None,
) -> list[dict[str, str]]:
    rows = annotations
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be >= 1")
        rows = rows[:limit]
    return rows


def _rate(count: int, total: int) -> str:
    if total <= 0:
        return "0.0000"
    return f"{count / total:.4f}"


def summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    parsed_rows = [row for row in rows if row.get("parse_ok")]
    validatable_rows = [row for row in parsed_rows if isinstance(row.get("parsed_output"), dict)]
    neutral_rows = [
        row for row in rows
        if row.get("expected_care_state") == "no_care"
    ]
    invalid_rows = [
        row for row in rows
        if row.get("expected_visible_state") == "invalid_observation"
    ]
    latencies = [
        float(row["latency_ms"]) for row in rows
        if isinstance(row.get("latency_ms"), (int, float))
    ]

    return {
        "total_samples": total,
        "json_parse_success_rate": _rate(sum(1 for row in rows if row.get("parse_ok")), total),
        "required_fields_present_rate": _rate(
            sum(1 for row in validatable_rows if row.get("required_fields_present")),
            total,
        ),
        "enum_valid_rate": _rate(sum(1 for row in validatable_rows if row.get("enum_valid")), total),
        "visible_state_accuracy": _rate(
            sum(1 for row in validatable_rows if row.get("visible_state_match")),
            total,
        ),
        "care_state_accuracy": _rate(
            sum(1 for row in validatable_rows if row.get("care_state_match")),
            total,
        ),
        "neutral_false_care_rate": _rate(
            sum(1 for row in neutral_rows if row.get("neutral_false_care")),
            len(neutral_rows),
        ),
        "invalid_observation_accuracy": _rate(
            sum(1 for row in invalid_rows if row.get("invalid_observation_match")),
            len(invalid_rows),
        ),
        "forbidden_claims_rate": _rate(
            sum(1 for row in validatable_rows if row.get("forbidden_claims_hit")),
            total,
        ),
        "avg_latency_ms": f"{(sum(latencies) / len(latencies)):.1f}" if latencies else "0.0",
        "timeout_count": sum(1 for row in rows if row.get("error") == "timeout"),
        "model_error_count": sum(1 for row in rows if row.get("error", "").startswith("model_error")),
        "parse_error_count": sum(1 for row in rows if row.get("error", "").startswith("json_parse_error")),
    }


def write_summary_csv(path: str | Path, summary: dict[str, Any]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerow({column: summary.get(column, "") for column in SUMMARY_COLUMNS})


def _load_image(image_path: Path):
    import cv2  # type: ignore[import-not-found]

    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"cannot read image: {image_path}")
    return image


def create_analyzer(model_path: str | None, device: str, face_crop: bool):
    ensure_repo_root_on_path()
    from base_station.perception.vlm_face_analyzer import VLMFaceAnalyzer

    if model_path:
        return VLMFaceAnalyzer(model_dir=model_path, device=device, face_crop=face_crop)
    return VLMFaceAnalyzer(device=device, face_crop=face_crop)


def infer_raw_output(analyzer: Any, image: Any, prompt: str) -> str:
    from base_station.perception import vlm_face_analyzer as vfa

    captured: dict[str, str] = {}
    original_prompt = vfa.PROMPT
    original_parse = vfa._parse

    def capture_parse(text: str) -> dict[str, Any]:
        captured["raw"] = text
        return original_parse(text)

    vfa.PROMPT = prompt
    vfa._parse = capture_parse
    try:
        result = analyzer.analyze_image(image)
    finally:
        vfa.PROMPT = original_prompt
        vfa._parse = original_parse
    return captured.get("raw", json.dumps(result, ensure_ascii=False))


def evaluate_images(
    annotations: list[dict[str, str]],
    root_dir: str | Path,
    prompt: str,
    analyzer: Any,
    repeat: int = 1,
    image_loader: Callable[[Path], Any] | None = None,
    infer: Callable[[Any, Any, str], str] | None = None,
) -> list[dict[str, Any]]:
    root = Path(root_dir)
    load = image_loader or _load_image
    run_infer = infer or infer_raw_output
    rows: list[dict[str, Any]] = []

    for label in annotations:
        image_path = root / label["image_path"]
        for run_index in range(repeat):
            started = time.perf_counter()
            raw_output = ""
            parsed: dict[str, Any] = {}
            parse_ok = False
            error = ""
            try:
                image = load(image_path)
                raw_output = run_infer(analyzer, image, prompt)
                parse_result = parse_vlm_output(raw_output)
                parse_ok = parse_result.ok
                parsed = parse_result.value
                error = parse_result.error
            except TimeoutError:
                error = "timeout"
            except Exception as exc:  # noqa: BLE001 - eval rows must preserve model failures.
                error = f"model_error: {exc}"

            latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
            validation = validate_output(parsed, label) if parse_ok else ValidationResult(
                required_fields_present=False,
                enum_valid=False,
                visible_state_match=False,
                care_state_match=False,
                forbidden_claims_hit=False,
                neutral_false_care=False,
                invalid_observation_match=None,
            )
            row = {
                "sample_id": label["sample_id"],
                "image_path": label["image_path"],
                "prompt_version": PROMPT_VERSION,
                "run_index": run_index,
                "raw_output": raw_output,
                "parsed_output": parsed,
                "latency_ms": latency_ms,
                "parse_ok": parse_ok,
                "error": error,
                "expected_visible_state": label.get("expected_visible_state", ""),
                "expected_care_state": label.get("expected_care_state", ""),
                "required_fields_present": validation.required_fields_present,
                "enum_valid": validation.enum_valid,
                "visible_state_match": validation.visible_state_match,
                "care_state_match": validation.care_state_match,
                "neutral_false_care": validation.neutral_false_care,
                "invalid_observation_match": validation.invalid_observation_match,
                "forbidden_claims_hit": validation.forbidden_claims_hit,
            }
            rows.append(row)

    return rows


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate offline VLM image JSON outputs.")
    parser.add_argument("--annotations", default=str(DEFAULT_ANNOTATIONS))
    parser.add_argument("--root-dir", default=str(EVAL_ROOT))
    parser.add_argument("--prompt-file", default=str(DEFAULT_PROMPT))
    parser.add_argument("--output-jsonl", default=str(DEFAULT_OUTPUTS))
    parser.add_argument("--summary-csv", default=str(DEFAULT_REPORT))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N annotation samples.")
    parser.add_argument("--model-path", default=None, help="Qwen2.5-VL OpenVINO model directory.")
    parser.add_argument("--device", default="CPU")
    parser.add_argument("--face-crop", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.repeat < 1:
            raise ValueError("--repeat must be >= 1")
        annotations = filter_annotations(
            load_annotations(args.annotations),
            limit=args.limit,
        )
        if not annotations:
            raise ValueError("no annotations selected")
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
        analyzer = create_analyzer(args.model_path, args.device, args.face_crop)
        rows = evaluate_images(annotations, args.root_dir, prompt, analyzer, repeat=args.repeat)
        write_jsonl(args.output_jsonl, rows)
        write_summary_csv(args.summary_csv, summarize_results(rows))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.output_jsonl}")
    print(f"Wrote {args.summary_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
