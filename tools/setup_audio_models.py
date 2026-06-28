#!/usr/bin/env python3
"""Prepare audio models for file-first ASR/VAD smoke tests.

Step 43.1 uses this lightweight tool for SenseVoiceSmall until the audio model
files have a stable sha256 manifest suitable for tools/setup_models.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

AUDIO_MODELS = {
    "sensevoice_small": {
        "repo_id": "FunAudioLLM/SenseVoiceSmall",
        "target_dir": REPO_ROOT / "base_station" / "models" / "sensevoice-small",
        "repo_type": "model",
        "public": True,
        "key_files": ("config.yaml", "model.pt", "configuration.json"),
        "ignore_patterns": ("image/*",),
    },
}


def _iter_files(path: Path) -> list[Path]:
    return [p for p in path.rglob("*") if p.is_file()]


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _local_summary(target_dir: Path, key_files: tuple[str, ...]) -> tuple[bool, int, int]:
    if not target_dir.exists():
        print(f"  MISSING directory: {target_dir}")
        return False, 0, 0
    if not target_dir.is_dir():
        print(f"  NOT A DIRECTORY: {target_dir}")
        return False, 0, 0

    files = _iter_files(target_dir)
    if not files:
        print(f"  EMPTY directory: {target_dir}")
        return False, 0, 0

    missing_key_files = [name for name in key_files if not (target_dir / name).is_file()]
    if missing_key_files:
        print(f"  WARNING missing expected SenseVoice key file(s): {missing_key_files}")

    total_bytes = sum(p.stat().st_size for p in files)
    print(f"  OK local directory: {target_dir}")
    print(f"  files={len(files)} size={_format_size(total_bytes)}")
    return True, len(files), total_bytes


def _download(spec: dict, *, force: bool) -> None:
    target_dir = spec["target_dir"]
    if target_dir.exists() and force:
        print(f"  force enabled; refreshing snapshot into {target_dir}")
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is required. Install it with: "
            ".venv/bin/python -m pip install -r base_station/requirements-audio.txt"
        ) from exc

    token = os.environ.get("HF_TOKEN")
    target_dir.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "repo_id": spec["repo_id"],
        "repo_type": spec.get("repo_type", "model"),
        "local_dir": str(target_dir),
        "token": token,
        "force_download": force,
        "ignore_patterns": spec.get("ignore_patterns"),
    }
    try:
        snapshot_download(local_dir_use_symlinks=False, **kwargs)
    except TypeError:
        snapshot_download(**kwargs)
    except PermissionError as exc:
        raise RuntimeError(f"permission error while writing model directory {target_dir}: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"filesystem or disk error while downloading to {target_dir}: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(
            "failed to download FunAudioLLM/SenseVoiceSmall from Hugging Face. "
            "Check network/proxy access, HF availability, disk space, and HF_TOKEN if the hub requires it. "
            f"Original error: {type(exc).__name__}: {exc}"
        ) from exc


def process(name: str, spec: dict, *, check_only: bool, force: bool) -> bool:
    print(f"[{name}] {spec['repo_id']}")
    if not check_only:
        _download(spec, force=force)
    ok, _count, _size = _local_summary(spec["target_dir"], spec["key_files"])
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="sensevoice_small", help="audio model key to process")
    parser.add_argument("--check", action="store_true", help="check local files only, no network")
    parser.add_argument("--force", action="store_true", help="force snapshot refresh")
    args = parser.parse_args(argv)

    if args.only not in AUDIO_MODELS:
        available = ", ".join(sorted(AUDIO_MODELS))
        print(f"unknown audio model key {args.only!r}; available: {available}", file=sys.stderr)
        return 2

    try:
        ok = process(args.only, AUDIO_MODELS[args.only], check_only=args.check, force=args.force)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if ok:
        print("Audio model check passed.")
        return 0
    print("Audio model check failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
