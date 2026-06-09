"""Check local/DK-2500 runtime prerequisites for Xiao An."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import platform
import sys
from typing import Any


PACKAGE_NAMES = ("cv2", "openvino", "funasr", "torch", "onnxruntime")
MODEL_PATHS = (
    "agent/data",
    "base_station/models",
    "base_station/models/sensevoice-small",
    "base_station/models/silero-vad",
    "base_station/models/qwen2_5_vl_openvino",
)


def find_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def check_python_version(min_version: tuple[int, int] = (3, 10)) -> dict:
    version_info = sys.version_info
    ok = (version_info.major, version_info.minor) >= min_version
    return {
        "version": platform.python_version(),
        "major": version_info.major,
        "minor": version_info.minor,
        "ok": ok,
        "minimum": f"{min_version[0]}.{min_version[1]}",
    }


def check_imports(package_names=PACKAGE_NAMES) -> dict:
    results = {}
    for package_name in package_names:
        try:
            importlib.import_module(package_name)
        except Exception as exc:  # Import can fail inside optional package init too.
            results[package_name] = {
                "status": "missing",
                "available": False,
                "error": str(exc),
            }
        else:
            results[package_name] = {
                "status": "available",
                "available": True,
            }
    return results


def check_paths(project_root: str | Path, relative_paths=MODEL_PATHS) -> dict:
    root = Path(project_root)
    results = {}
    for relative_path in relative_paths:
        path = root / relative_path
        exists = path.exists()
        results[relative_path] = {
            "status": "exists" if exists else "missing",
            "exists": exists,
            "path": str(path),
        }
    return results


def check_camera(camera_index: int = 0) -> dict:
    result = {
        "checked": True,
        "ok": False,
        "camera_index": camera_index,
    }
    try:
        cv2 = importlib.import_module("cv2")
    except Exception as exc:
        result.update({
            "reason": "cv2_missing",
            "error": str(exc),
        })
        return result

    capture = cv2.VideoCapture(camera_index)
    try:
        is_opened = getattr(capture, "isOpened", lambda: True)
        if not is_opened():
            result["reason"] = "camera_open_failed"
            return result

        ok, frame = capture.read()
        if not ok:
            result["reason"] = "frame_read_failed"
            return result

        height, width = _frame_size(frame)
        result.update({
            "ok": True,
            "reason": "ok",
            "width": width,
            "height": height,
        })
        return result
    finally:
        release = getattr(capture, "release", None)
        if callable(release):
            release()


def _frame_size(frame: Any) -> tuple[int | None, int | None]:
    shape = getattr(frame, "shape", None)
    if shape is not None and len(shape) >= 2:
        return int(shape[0]), int(shape[1])
    return None, None


def build_report(
    project_root: str | Path | None = None,
    check_camera_enabled: bool = False,
    camera_index: int = 0,
) -> dict:
    root = Path(project_root) if project_root is not None else find_project_root()
    python_result = check_python_version()
    packages = check_imports()
    paths = check_paths(root)
    camera = (
        check_camera(camera_index=camera_index)
        if check_camera_enabled
        else {"checked": False, "ok": None, "camera_index": camera_index}
    )
    overall_status = _overall_status(python_result, packages, paths, camera)
    return {
        "project_root": str(root),
        "python": python_result,
        "packages": packages,
        "paths": paths,
        "camera": camera,
        "overall_status": overall_status,
    }


def _overall_status(python_result: dict, packages: dict, paths: dict, camera: dict) -> str:
    if not python_result.get("ok", False):
        return "error"
    if camera.get("checked") and not camera.get("ok", False):
        return "error"
    if any(package.get("status") == "missing" for package in packages.values()):
        return "warning"
    if any(path.get("status") == "missing" for path in paths.values()):
        return "warning"
    return "ok"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Xiao An runtime environment.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--check-camera", action="store_true", help="Try to open and read from a camera.")
    parser.add_argument("--camera-index", type=int, default=0, help="Camera index for --check-camera.")
    parser.add_argument("--project-root", default=None, help="Project root path. Defaults to auto-detected root.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        project_root=args.project_root,
        check_camera_enabled=args.check_camera,
        camera_index=args.camera_index,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
