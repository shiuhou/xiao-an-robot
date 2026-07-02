#!/usr/bin/env python3
"""Download xiao-an model weights from Hugging Face to their correct paths.

Big model weights are NOT committed to git. They live in public Hugging Face
repos and are fetched here, into the exact layout the runtime expects under
``base_station/models/``. Every downloaded file is verified against the sha256
recorded in ``base_station/models/models_manifest.json``.

(The OpenFace OV IR under ``base_station/models/openface_ov/`` is the one
exception: it is small and integration-critical, so it ships inside the repo via
git LFS and is NOT handled here. Run ``git lfs pull`` if it is missing.)

Usage
-----
    python tools/setup_models.py              # download + verify everything
    python tools/setup_models.py --only qwen_vl
    python tools/setup_models.py --check      # verify local files only, no download
    python tools/setup_models.py --force      # re-download even if present

All repos are public, so no token is needed. If you later make a repo private,
set HF_TOKEN in the environment and it will be used automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "base_station" / "models" / "models_manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    if not MANIFEST.is_file():
        sys.exit(f"manifest not found: {MANIFEST}")
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def _verify(target_dir: Path, files: dict) -> tuple[list[str], list[str]]:
    """Return (missing, corrupt) relative paths."""
    missing, corrupt = [], []
    for rel, meta in files.items():
        p = target_dir / rel
        if not p.is_file():
            missing.append(rel)
            continue
        if p.stat().st_size != meta["size"] or _sha256(p) != meta["sha256"]:
            corrupt.append(rel)
    return missing, corrupt


def _download(repo_id: str, repo_type: str, target_dir: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit(
            "huggingface_hub is required. Install it with:\n"
            "    pip install -r base_station/requirements-vlm.txt\n"
            "  (or: pip install 'huggingface_hub==0.36.2')"
        )
    token = os.environ.get("HF_TOKEN")  # None for public repos
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {repo_id} -> {target_dir} ...")
    snapshot_download(
        repo_id=repo_id,
        repo_type=repo_type,
        local_dir=str(target_dir),
        token=token,
    )


def process(name: str, spec: dict, *, check_only: bool, force: bool) -> bool:
    target_dir = REPO_ROOT / spec["target_dir"]
    files = spec["files"]
    print(f"[{name}] {spec['repo_id']}")

    if not check_only:
        missing, corrupt = _verify(target_dir, files)
        if force or missing or corrupt:
            _download(spec["repo_id"], spec.get("repo_type", "model"), target_dir)

    missing, corrupt = _verify(target_dir, files)
    if missing or corrupt:
        if missing:
            print(f"  MISSING {len(missing)} file(s): {missing[:3]}{' ...' if len(missing) > 3 else ''}")
        if corrupt:
            print(f"  CORRUPT {len(corrupt)} file(s): {corrupt[:3]}{' ...' if len(corrupt) > 3 else ''}")
        return False
    total_mb = round(sum(m["size"] for m in files.values()) / 1e6, 1)
    print(f"  OK  {len(files)} files, {total_mb} MB verified")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="process a single repo key (e.g. qwen_vl, base_models)")
    ap.add_argument("--check", action="store_true", help="verify local files only, do not download")
    ap.add_argument("--force", action="store_true", help="re-download even if files already verify")
    args = ap.parse_args()

    manifest = _load_manifest()
    repos = manifest["repos"]
    if args.only:
        if args.only not in repos:
            sys.exit(f"unknown repo key {args.only!r}; available: {', '.join(repos)}")
        repos = {args.only: repos[args.only]}

    ok = True
    for name, spec in repos.items():
        ok &= process(name, spec, check_only=args.check, force=args.force)
        print()

    if ok:
        print("All models present and verified.")
        return 0
    print("Some models are missing or corrupt. Re-run without --check to (re)download.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
