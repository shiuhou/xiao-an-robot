"""Prepare local TTS cache for Integration Console Fast Demo Mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from base_station.integration_console.fast_demo_brain import iter_fast_demo_tts_texts
from base_station.perception.audio_diagnostics import pcm_s16le_stats
from base_station.ws_server.tts_stream import (
    synthesize_tts_pcm_stream,
    tts_cache_path_for_text,
    tts_robot_pcm_cache_path_for_text,
    tts_target_peak_from_env,
)


def prepare_fast_demo_tts_cache(
    *,
    runtime_dir: Path,
    manifest_path: Path,
    include_visual_normal: bool = True,
    fail_fast: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    target_peak = tts_target_peak_from_env()
    items: list[dict[str, Any]] = []
    ok_count = 0
    failed_count = 0
    for entry in iter_fast_demo_tts_texts(include_visual_normal=include_visual_normal):
        text = entry["text"]
        wav_cache_path = tts_cache_path_for_text(text, runtime_dir=runtime_dir)
        pcm_cache_path = tts_robot_pcm_cache_path_for_text(
            text,
            runtime_dir=runtime_dir,
            target_peak=target_peak,
        )
        item = dict(entry)
        item["cache_path"] = str(pcm_cache_path)
        item["robot_pcm_cache_path"] = str(pcm_cache_path)
        item["wav_cache_path"] = str(wav_cache_path)
        item["format"] = "raw pcm_s16le"
        item["sample_rate"] = 16000
        item["channels"] = 1
        item["sample_width_bytes"] = 2
        item["target_peak"] = target_peak
        item["speaker_stream_gain"] = 32
        item["cache_payload"] = "robot_ready_raw_pcm_s16le"
        item["cached_before"] = pcm_cache_path.exists() and pcm_cache_path.stat().st_size > 0
        item_started = time.monotonic()
        try:
            stream = synthesize_tts_pcm_stream(text, runtime_dir=runtime_dir)
        except Exception as exc:
            failed_count += 1
            item.update({
                "ok": False,
                "error": str(exc),
                "elapsed_sec": round(time.monotonic() - item_started, 3),
            })
            items.append(item)
            if fail_fast:
                break
            continue
        cache_exists = pcm_cache_path.exists() and pcm_cache_path.stat().st_size > 0
        pcm_stats = pcm_s16le_stats(
            pcm_cache_path.read_bytes() if cache_exists else stream.pcm,
            sample_rate=stream.sample_rate,
            channels=stream.channels,
        )
        item.update({
            "ok": cache_exists,
            "cached_after": cache_exists,
            "pcm_bytes": len(stream.pcm),
            "duration_ms": stream.duration_ms,
            "peak": pcm_stats["peak"],
            "rms": pcm_stats["rms"],
            "elapsed_sec": round(time.monotonic() - item_started, 3),
        })
        if cache_exists and stream.sample_rate == 16000 and stream.channels == 1 and pcm_stats["peak"] <= target_peak:
            ok_count += 1
        else:
            failed_count += 1
            item["error"] = "robot_pcm_cache_invalid_after_synthesis"
        items.append(item)

    manifest = {
        "schema_version": "xiaoan.fast_demo_tts_manifest.v2",
        "runtime_dir": str(runtime_dir),
        "manifest_path": str(manifest_path),
        "include_visual_normal": include_visual_normal,
        "format": "raw pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "sample_width_bytes": 2,
        "target_peak": target_peak,
        "speaker_stream_gain": 32,
        "cache_payload": "robot_ready_raw_pcm_s16le",
        "total": len(items),
        "ok_count": ok_count,
        "failed_count": failed_count,
        "elapsed_sec": round(time.monotonic() - started, 3),
        "items": items,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare cached Fast Demo robot-ready raw PCM files.")
    parser.add_argument("--runtime-dir", default="runtime")
    parser.add_argument("--manifest-path", default="runtime/integration_console/fast_demo/tts_manifest.json")
    parser.add_argument("--exclude-visual-normal", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = prepare_fast_demo_tts_cache(
        runtime_dir=Path(args.runtime_dir),
        manifest_path=Path(args.manifest_path),
        include_visual_normal=not args.exclude_visual_normal,
        fail_fast=args.fail_fast,
    )
    print(json.dumps({
        "ok": manifest["failed_count"] == 0,
        "total": manifest["total"],
        "ok_count": manifest["ok_count"],
        "failed_count": manifest["failed_count"],
        "elapsed_sec": manifest["elapsed_sec"],
        "manifest_path": manifest["manifest_path"],
    }, ensure_ascii=False, indent=2))
    return 0 if manifest["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
