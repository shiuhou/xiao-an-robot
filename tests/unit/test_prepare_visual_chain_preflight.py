"""Unit tests for visual-chain preflight checks."""

from __future__ import annotations

from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import prepare_visual_chain_preflight as preflight


def write_test_png(path: Path) -> None:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:
        raise unittest.SkipTest(f"OpenCV/numpy not available for image fixture: {exc}") from exc
    image = np.zeros((2, 3, 3), dtype=np.uint8)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"failed to write {path}")


class PrepareVisualChainPreflightTest(unittest.TestCase):
    def test_parse_args_accepts_real_runtime_options(self) -> None:
        args = preflight.parse_args([
            "--image-path",
            "runtime/latest.jpg",
            "--run-openface",
            "--run-qwen",
            "--check-openclaw",
            "--json",
        ])

        self.assertEqual(args.image_path, "runtime/latest.jpg")
        self.assertTrue(args.run_openface)
        self.assertTrue(args.run_qwen)
        self.assertTrue(args.check_openclaw)
        self.assertTrue(args.json)

    def test_image_decode_reports_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            write_test_png(image_path)

            result = preflight.check_image_decode(image_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["width"], 3)
        self.assertEqual(result["height"], 2)

    def test_image_decode_missing_file_is_failure(self) -> None:
        result = preflight.check_image_decode(Path("missing.jpg"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "fail")
        self.assertIn("does not exist", result["error"])

    def test_openface_readiness_reports_missing_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models = root / "models"
            for relative in preflight.OPENFACE_MODEL_FILES:
                path = models / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
            runtime = root / "runtime"
            runtime.mkdir()

            with patch("tools.ops.prepare_visual_chain_preflight.check_imports") as imports:
                imports.return_value = {
                    "cv2": {"ok": True},
                    "torchvision": {"ok": False, "error": "missing"},
                }
                result = preflight.check_openface_readiness(runtime, models)

        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_model_files"], [])
        self.assertFalse(result["imports"]["torchvision"]["ok"])

    def test_openface_readiness_rejects_lfs_pointer_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models = root / "models"
            for relative in preflight.OPENFACE_MODEL_FILES:
                path = models / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"model-bytes")
            (models / preflight.OPENFACE_MODEL_FILES[0]).write_text(
                "version https://git-lfs.github.com/spec/v1\n"
                "oid sha256:abc\n"
                "size 123\n",
                encoding="utf-8",
            )
            runtime = root / "runtime"
            runtime.mkdir()

            with patch("tools.ops.prepare_visual_chain_preflight.check_imports") as imports:
                imports.return_value = {name: {"ok": True} for name in preflight.OPENFACE_IMPORTS}
                result = preflight.check_openface_readiness(runtime, models)

        self.assertFalse(result["ok"])
        self.assertEqual(result["lfs_pointer_model_files"], [preflight.OPENFACE_MODEL_FILES[0]])

    def test_qwen_readiness_missing_model_dir_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("tools.ops.prepare_visual_chain_preflight.check_imports") as imports:
                imports.return_value = {name: {"ok": True} for name in preflight.QWEN_IMPORTS}
                result = preflight.check_qwen_readiness(Path(temp_dir) / "missing-qwen")

        self.assertFalse(result["ok"])
        self.assertFalse(result["model_dir_exists"])
        self.assertIn("requirements-vlm.txt", result["next_fix"])
        self.assertIn("setup_models.py --only qwen_vl", result["next_fix"])

    def test_timeout_output_tail_is_json_serializable(self) -> None:
        def raise_timeout(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd=["demo"], timeout=1, output=b"hello\nworld\n")

        with patch("tools.ops.prepare_visual_chain_preflight.subprocess.run", side_effect=raise_timeout):
            result = preflight.run_command(["demo"], timeout_seconds=1)

        self.assertFalse(result["ok"])
        self.assertEqual(result["output_tail"], "hello\nworld\n")
        json.dumps(result)

    def test_qwen_readiness_reports_bad_manifest_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "base_station" / "models" / "models_manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{bad json", encoding="utf-8")
            model_dir = root / "base_station" / "models" / "Qwen2.5-VL-3B-OV-int4"
            model_dir.mkdir()
            (model_dir / "openvino_model.xml").write_text("<xml/>", encoding="utf-8")
            (model_dir / "openvino_model.bin").write_bytes(b"model")

            with patch.object(preflight, "REPO_ROOT", root):
                with patch("tools.ops.prepare_visual_chain_preflight.check_imports") as imports:
                    imports.return_value = {name: {"ok": True} for name in preflight.QWEN_IMPORTS}
                    result = preflight.check_qwen_readiness(model_dir)

        self.assertFalse(result["ok"])
        self.assertIn("manifest_error", result)
        self.assertTrue(result["manifest_error"])

    def test_build_report_resolves_relative_model_paths_from_repo_root(self) -> None:
        args = preflight.parse_args([
            "--image-path",
            "runtime/latest.jpg",
            "--openface-runtime",
            "relative/openface_runtime",
            "--openface-models-dir",
            "relative/openface_models",
            "--qwen-model-path",
            "relative/qwen",
        ])

        with patch("tools.ops.prepare_visual_chain_preflight.check_image_decode") as image:
            with patch("tools.ops.prepare_visual_chain_preflight.check_mock_runtime") as mock_runtime:
                with patch("tools.ops.prepare_visual_chain_preflight.check_openface_readiness") as openface:
                    with patch("tools.ops.prepare_visual_chain_preflight.check_qwen_readiness") as qwen:
                        image.return_value = {"name": "image_decode", "ok": True}
                        mock_runtime.return_value = {"name": "mock_image_runtime", "ok": True}
                        openface.return_value = {"name": "openface_ov_readiness", "ok": True}
                        qwen.return_value = {"name": "qwen_vl_openvino_readiness", "ok": True}
                        report = preflight.build_report(args)

        self.assertEqual(report["image_path"], "runtime/latest.jpg")
        openface_args = openface.call_args.args
        qwen_args = qwen.call_args.args
        self.assertEqual(openface_args[0], preflight.REPO_ROOT / "relative/openface_runtime")
        self.assertEqual(openface_args[1], preflight.REPO_ROOT / "relative/openface_models")
        self.assertEqual(qwen_args[0], preflight.REPO_ROOT / "relative/qwen")


if __name__ == "__main__":
    unittest.main()
