"""Preflight checks for Demo 1 visual-chain work.

This tool is intentionally camera-free by default. It validates the pieces that
can be prepared before a fresh robot ``runtime/latest.jpg`` is available:

* static image decode and ``emotion_runtime --source image_file`` wiring
* OpenFace OV runtime files, model files, and Python imports
* Qwen2.5-VL OpenVINO model files and Python imports
* optional OpenClaw Gateway socket reachability

Use ``--image-path runtime/latest.jpg`` once the robot camera is online.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

from base_station.perception.static_image_source import load_static_image


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE_CANDIDATES = (
    REPO_ROOT / "runtime" / "manual_samples" / "vision_real_camera_0703.jpg",
    REPO_ROOT / "runtime" / "latest.jpg",
)
DEFAULT_OPENFACE_RUNTIME = REPO_ROOT / "base_station" / "perception" / "openface_ov_runtime"
DEFAULT_OPENFACE_MODELS = REPO_ROOT / "base_station" / "models" / "openface_ov"
DEFAULT_QWEN_MODEL = REPO_ROOT / "base_station" / "models" / "Qwen2.5-VL-3B-OV-int4"
DEFAULT_REPORT_OUT = REPO_ROOT / "runtime" / "visual_chain_preflight.json"

OPENFACE_MODEL_FILES = (
    "retinaface/retinaface.xml",
    "retinaface/retinaface.bin",
    "star/star.xml",
    "star/star.bin",
    "mtl/mtl.xml",
    "mtl/mtl.bin",
)
OPENFACE_IMPORTS = ("cv2", "numpy", "torch", "torchvision", "openvino")
QWEN_IMPORTS = ("transformers", "optimum.intel.openvino", "qwen_vl_utils", "PIL")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _status(ok: bool, *, skipped: bool = False) -> str:
    if skipped:
        return "skip"
    return "pass" if ok else "fail"


def _short_error(exc: BaseException, limit: int = 260) -> str:
    message = " ".join(str(exc).split())
    if len(message) > limit:
        return message[: limit - 3] + "..."
    return message


def _output_tail(output: str | bytes | None, limit: int = 3000) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    return output[-limit:]


def _repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def find_default_image() -> Path:
    for candidate in DEFAULT_IMAGE_CANDIDATES:
        if candidate.is_file():
            return candidate
    return DEFAULT_IMAGE_CANDIDATES[0]


def check_imports(module_names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name in module_names:
        try:
            importlib.import_module(name)
        except Exception as exc:
            results[name] = {
                "ok": False,
                "status": "missing",
                "error": _short_error(exc),
            }
        else:
            results[name] = {"ok": True, "status": "available"}
    return results


def missing_files(root: Path, relative_files: tuple[str, ...] | list[str]) -> list[str]:
    return [relative for relative in relative_files if not (root / relative).is_file()]


def lfs_pointer_files(root: Path, relative_files: tuple[str, ...] | list[str]) -> list[str]:
    pointers: list[str] = []
    for relative in relative_files:
        path = root / relative
        if not path.is_file():
            continue
        try:
            prefix = path.read_bytes()[:80]
        except OSError:
            continue
        if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
            pointers.append(relative)
    return pointers


def check_image_decode(image_path: Path) -> dict[str, Any]:
    try:
        payload, width, height = load_static_image(image_path)
    except Exception as exc:
        return {
            "name": "image_decode",
            "status": "fail",
            "ok": False,
            "image_path": _rel(image_path),
            "error": _short_error(exc),
        }
    return {
        "name": "image_decode",
        "status": "pass",
        "ok": True,
        "image_path": _rel(image_path),
        "width": width,
        "height": height,
        "payload_type": type(payload).__name__,
    }


def run_command(command: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "status": "fail",
            "exit_code": None,
            "timeout_seconds": timeout_seconds,
            "output_tail": _output_tail(exc.stdout),
            "error": f"timed out after {timeout_seconds}s",
        }

    return {
        "ok": completed.returncode == 0,
        "status": _status(completed.returncode == 0),
        "exit_code": completed.returncode,
        "output_tail": _output_tail(completed.stdout),
    }


def check_mock_runtime(image_path: Path, timeout_seconds: int) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "base_station.monitor.emotion_runtime",
        "--source",
        "image_file",
        "--image-path",
        str(image_path),
        "--model-backend",
        "mock",
        "--pattern",
        "tired",
        "--enable-vlm-gate",
        "--vlm-backend",
        "fake",
        "--force-vlm",
        "--count",
        "1",
        "--no-agent",
        "--verbose",
    ]
    result = run_command(command, timeout_seconds=timeout_seconds)
    result.update({
        "name": "mock_image_runtime",
        "command": " ".join(command),
    })
    return result


def check_openface_readiness(openface_runtime: Path, openface_models: Path) -> dict[str, Any]:
    missing_model_files = missing_files(openface_models, OPENFACE_MODEL_FILES)
    pointer_model_files = lfs_pointer_files(openface_models, OPENFACE_MODEL_FILES)
    import_results = check_imports(OPENFACE_IMPORTS)
    ok = (
        openface_runtime.is_dir()
        and openface_models.is_dir()
        and not missing_model_files
        and not pointer_model_files
        and all(result["ok"] for result in import_results.values())
    )
    return {
        "name": "openface_ov_readiness",
        "status": _status(ok),
        "ok": ok,
        "runtime_dir": _rel(openface_runtime),
        "runtime_dir_exists": openface_runtime.is_dir(),
        "models_dir": _rel(openface_models),
        "models_dir_exists": openface_models.is_dir(),
        "missing_model_files": missing_model_files,
        "lfs_pointer_model_files": pointer_model_files,
        "imports": import_results,
        "next_fix": (
            "Install git-lfs, run `git lfs pull`, and install `.venv` vision requirements if imports are missing."
            if not ok
            else ""
        ),
    }


def check_qwen_readiness(qwen_model_dir: Path) -> dict[str, Any]:
    manifest = REPO_ROOT / "base_station" / "models" / "models_manifest.json"
    missing_manifest_files: list[str] = []
    manifest_error = ""
    if manifest.is_file():
        try:
            with manifest.open(encoding="utf-8") as f:
                data = json.load(f)
            qwen_spec = data.get("repos", {}).get("qwen_vl", {})
            missing_manifest_files = missing_files(qwen_model_dir, list(qwen_spec.get("files", {}).keys()))
        except (OSError, json.JSONDecodeError) as exc:
            manifest_error = _short_error(exc)

    top_level_xml = list(qwen_model_dir.glob("*.xml")) if qwen_model_dir.is_dir() else []
    top_level_bin = list(qwen_model_dir.glob("*.bin")) if qwen_model_dir.is_dir() else []
    import_results = check_imports(QWEN_IMPORTS)
    ok = (
        qwen_model_dir.is_dir()
        and not manifest_error
        and not missing_manifest_files
        and bool(top_level_xml)
        and bool(top_level_bin)
        and all(result["ok"] for result in import_results.values())
    )
    return {
        "name": "qwen_vl_openvino_readiness",
        "status": _status(ok),
        "ok": ok,
        "model_dir": _rel(qwen_model_dir),
        "model_dir_exists": qwen_model_dir.is_dir(),
        "manifest_path": _rel(manifest),
        "manifest_error": manifest_error,
        "missing_manifest_files_count": len(missing_manifest_files),
        "missing_manifest_files_sample": missing_manifest_files[:8],
        "has_top_level_xml": bool(top_level_xml),
        "has_top_level_bin": bool(top_level_bin),
        "imports": import_results,
        "next_fix": (
            "Run `.venv/bin/python -m pip install -r base_station/requirements-vlm.txt`, then "
            "`.venv/bin/python tools/setup_models.py --only qwen_vl`."
            if not ok
            else ""
        ),
    }


def check_openclaw_socket(gateway_url: str, timeout_seconds: float = 2.0) -> dict[str, Any]:
    parsed = urlparse(gateway_url)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return {
            "name": "openclaw_socket",
            "status": "fail",
            "ok": False,
            "gateway_url": gateway_url,
            "error": "gateway URL must include host and port",
        }
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass
    except OSError as exc:
        return {
            "name": "openclaw_socket",
            "status": "fail",
            "ok": False,
            "gateway_url": gateway_url,
            "error": _short_error(exc),
        }
    return {
        "name": "openclaw_socket",
        "status": "pass",
        "ok": True,
        "gateway_url": gateway_url,
    }


def check_openface_runtime(image_path: Path, timeout_seconds: int) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "base_station.monitor.emotion_runtime",
        "--source",
        "image_file",
        "--image-path",
        str(image_path),
        "--model-backend",
        "openface_ov",
        "--count",
        "1",
        "--no-agent",
        "--verbose",
    ]
    result = run_command(command, timeout_seconds=timeout_seconds)
    result.update({
        "name": "openface_ov_runtime",
        "command": " ".join(command),
    })
    return result


def check_qwen_runtime(image_path: Path, qwen_model_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "base_station.monitor.emotion_runtime",
        "--source",
        "image_file",
        "--image-path",
        str(image_path),
        "--model-backend",
        "mock",
        "--pattern",
        "tired",
        "--enable-vlm-gate",
        "--vlm-backend",
        "openvino_qwen_vl",
        "--vlm-model-path",
        str(qwen_model_dir),
        "--force-vlm",
        "--count",
        "1",
        "--no-agent",
        "--verbose",
    ]
    result = run_command(command, timeout_seconds=timeout_seconds)
    result.update({
        "name": "qwen_vl_openvino_runtime",
        "command": " ".join(command),
    })
    return result


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    image_path = _repo_path(args.image_path) if args.image_path else find_default_image()
    openface_runtime = _repo_path(args.openface_runtime)
    openface_models = _repo_path(args.openface_models_dir)
    qwen_model_dir = _repo_path(args.qwen_model_path)
    steps = [
        check_image_decode(image_path),
        check_mock_runtime(image_path, timeout_seconds=args.timeout_seconds),
        check_openface_readiness(openface_runtime, openface_models),
        check_qwen_readiness(qwen_model_dir),
    ]
    if args.check_openclaw:
        steps.append(check_openclaw_socket(args.openclaw_gateway_url))
    if args.run_openface:
        steps.append(check_openface_runtime(image_path, timeout_seconds=args.real_timeout_seconds))
    if args.run_qwen:
        steps.append(check_qwen_runtime(image_path, qwen_model_dir, timeout_seconds=args.real_timeout_seconds))

    return {
        "schema": "xiao-an.visual-preflight.v1",
        "project_root": str(REPO_ROOT),
        "image_path": _rel(image_path),
        "steps": steps,
        "overall_status": "pass" if all(step.get("ok") for step in steps) else "fail",
    }


def print_human(report: dict[str, Any]) -> None:
    print(f"visual preflight: {report['overall_status']}")
    print(f"image: {report['image_path']}")
    for step in report["steps"]:
        marker = "PASS" if step.get("ok") else "FAIL"
        print(f"- {marker} {step['name']}")
        if step.get("error"):
            print(f"  error: {step['error']}")
        if step.get("missing_model_files"):
            print(f"  missing model files: {step['missing_model_files'][:5]}")
        if step.get("lfs_pointer_model_files"):
            print(f"  git-lfs pointer files: {step['lfs_pointer_model_files'][:5]}")
        if step.get("missing_manifest_files_count"):
            print(
                "  missing qwen files: "
                f"{step['missing_manifest_files_count']} "
                f"{step.get('missing_manifest_files_sample')}"
            )
        if step.get("manifest_error"):
            print(f"  manifest error: {step['manifest_error']}")
        imports = step.get("imports") or {}
        missing_imports = [name for name, result in imports.items() if not result.get("ok")]
        if missing_imports:
            print(f"  missing imports: {missing_imports}")
        if step.get("next_fix"):
            print(f"  next: {step['next_fix']}")
        if step.get("exit_code") not in (None, 0):
            print(f"  exit_code: {step['exit_code']}")
        if step.get("output_tail"):
            tail = str(step["output_tail"]).strip().splitlines()[-5:]
            for line in tail:
                print(f"  | {line}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare/check the Demo 1 visual chain before robot camera capture.")
    parser.add_argument("--image-path", default=None, help="Static image to use. Defaults to runtime/manual_samples/vision_real_camera_0703.jpg or runtime/latest.jpg.")
    parser.add_argument("--openface-runtime", default=str(DEFAULT_OPENFACE_RUNTIME), help="Bundled OpenFace OV runtime path.")
    parser.add_argument("--openface-models-dir", default=str(DEFAULT_OPENFACE_MODELS), help="OpenFace OV IR model directory.")
    parser.add_argument("--qwen-model-path", default=str(DEFAULT_QWEN_MODEL), help="Qwen2.5-VL OpenVINO model directory.")
    parser.add_argument("--run-openface", action="store_true", help="Actually run emotion_runtime with --model-backend openface_ov.")
    parser.add_argument("--run-qwen", action="store_true", help="Actually run emotion_runtime with --vlm-backend openvino_qwen_vl.")
    parser.add_argument("--check-openclaw", action="store_true", help="Check TCP reachability of the OpenClaw Gateway URL.")
    parser.add_argument("--openclaw-gateway-url", default="ws://127.0.0.1:18789", help="OpenClaw Gateway URL for --check-openclaw.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="Timeout for quick runtime checks.")
    parser.add_argument("--real-timeout-seconds", type=int, default=180, help="Timeout for real OpenFace/Qwen runtime checks.")
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT_OUT), help="Write JSON report to this path.")
    parser.add_argument("--json", action="store_true", help="Print only JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
        print(f"report: {_rel(report_out)}")
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
