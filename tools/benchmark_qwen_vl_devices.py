#!/usr/bin/env python
"""Benchmark Qwen2.5-VL OpenVINO latency across OpenVINO devices."""

from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from base_station.perception.openvino_qwen_vl_emotion_model import OpenVINOQwenVLEmotionModel
from base_station.perception.qwen_vl_openvino_runner import QwenVLOpenVINORunner
from base_station.perception.static_image_source import StaticImageFrameSource


DEFAULT_MODEL_DIR = "base_station/models/Qwen2.5-VL-3B-OV-int4"
DEFAULT_PATTERNS = (
    "runtime/manual_samples/*.png",
    "runtime/manual_samples/*.jpg",
    "runtime/manual_samples/*.jpeg",
    "runtime/latest.jpg",
    "runtime/integration_console/visual/*.jpg",
    "runtime/integration_console/fast_demo/visual/*.jpg",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", default=DEFAULT_MODEL_DIR)
    parser.add_argument("--device", action="append", default=None, help="OpenVINO device to test. Repeatable.")
    parser.add_argument("--image", action="append", default=None, help="Image path or glob. Repeatable.")
    parser.add_argument("--limit", type=int, default=6, help="Maximum image count after glob expansion.")
    parser.add_argument("--repeats", type=int, default=1, help="Measured repeats per image.")
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be positive")
    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    if args.max_new_tokens <= 0:
        parser.error("--max-new-tokens must be positive")
    return args


def expand_images(patterns: list[str] | None, *, limit: int) -> list[Path]:
    selected = patterns or list(DEFAULT_PATTERNS)
    images: list[Path] = []
    seen: set[Path] = set()
    for item in selected:
        matches = [Path(match) for match in sorted(glob.glob(item))] if any(char in item for char in "*?[]") else [Path(item)]
        for path in matches:
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            images.append(path)
            if len(images) >= limit:
                return images
    return images


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    devices = sorted({str(row["device"]) for row in rows})
    for device in devices:
        values = [float(row["latency_ms"]) for row in rows if row["device"] == device and row.get("ok")]
        summaries.append({
            "device": device,
            "samples": len(values),
            "mean_ms": round(statistics.mean(values), 2) if values else None,
            "median_ms": round(statistics.median(values), 2) if values else None,
            "p90_ms": round(percentile(values, 0.9), 2) if values else None,
            "min_ms": round(min(values), 2) if values else None,
            "max_ms": round(max(values), 2) if values else None,
        })
    return summaries


def benchmark_device(
    *,
    device: str,
    model_dir: str,
    images: list[Path],
    repeats: int,
    max_new_tokens: int,
    verbose: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    load_started = time.perf_counter()
    runner = QwenVLOpenVINORunner(model_dir=model_dir, device=device, max_new_tokens=max_new_tokens)
    model = OpenVINOQwenVLEmotionModel(runner)
    model.preload()
    load_ms = (time.perf_counter() - load_started) * 1000.0

    rows: list[dict[str, Any]] = []
    for image_path in images:
        frame = StaticImageFrameSource(str(image_path), count=1, interval_seconds=0).read_frame()
        for repeat in range(repeats):
            started = time.perf_counter()
            ok = True
            error = None
            sample: dict[str, Any] | None = None
            try:
                sample = model.predict(frame)
            except Exception as exc:  # noqa: BLE001 - benchmark should keep going.
                ok = False
                error = f"{type(exc).__name__}: {exc}"
            latency_ms = (time.perf_counter() - started) * 1000.0
            row = {
                "device": device,
                "image_path": str(image_path),
                "repeat": repeat + 1,
                "ok": ok,
                "latency_ms": round(latency_ms, 2),
                "emotion_tag": sample.get("emotion_tag") if sample else None,
                "confidence": sample.get("confidence") if sample else None,
                "fatigue_score": sample.get("fatigue_score") if sample else None,
                "error": error,
            }
            rows.append(row)
            if verbose:
                print(json.dumps(row, ensure_ascii=False), flush=True)

    return {"device": device, "load_ms": round(load_ms, 2)}, rows


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    images = expand_images(args.image, limit=args.limit)
    if not images:
        print("Error: no benchmark images found.", file=sys.stderr)
        return 1

    devices = args.device or ["CPU", "GPU"]
    loads: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for device in devices:
        try:
            load, device_rows = benchmark_device(
                device=device,
                model_dir=args.model_dir,
                images=images,
                repeats=args.repeats,
                max_new_tokens=args.max_new_tokens,
                verbose=args.verbose,
            )
            loads.append(load)
            rows.extend(device_rows)
        except Exception as exc:  # noqa: BLE001 - report device-level failures.
            loads.append({
                "device": device,
                "load_ms": None,
                "error": f"{type(exc).__name__}: {exc}",
            })

    output = {
        "model_dir": args.model_dir,
        "max_new_tokens": args.max_new_tokens,
        "images": [str(path) for path in images],
        "loads": loads,
        "summary": summarize(rows),
        "rows": rows,
    }
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.csv_out:
        write_csv(args.csv_out, rows)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
