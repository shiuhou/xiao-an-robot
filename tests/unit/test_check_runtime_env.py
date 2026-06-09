"""Unit tests for tools/check_runtime_env.py."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from tools import check_runtime_env


class FakeFrame:
    shape = (480, 640, 3)


class FakeVideoCapture:
    def __init__(self, camera_index: int):
        self.camera_index = camera_index
        self.released = False

    def isOpened(self) -> bool:
        return True

    def read(self):
        return True, FakeFrame()

    def release(self) -> None:
        self.released = True


class CheckRuntimeEnvTest(unittest.TestCase):
    def test_check_python_version_contains_version_and_ok(self) -> None:
        result = check_runtime_env.check_python_version()

        self.assertIn("version", result)
        self.assertIn("ok", result)
        self.assertIsInstance(result["ok"], bool)

    def test_check_imports_reports_existing_json_module_available(self) -> None:
        result = check_runtime_env.check_imports(["json"])

        self.assertEqual(result["json"]["status"], "available")
        self.assertTrue(result["json"]["available"])

    def test_check_imports_reports_missing_module_without_raising(self) -> None:
        result = check_runtime_env.check_imports(["xiao_an_missing_module_for_test"])

        self.assertEqual(result["xiao_an_missing_module_for_test"]["status"], "missing")
        self.assertFalse(result["xiao_an_missing_module_for_test"]["available"])
        self.assertIn("error", result["xiao_an_missing_module_for_test"])

    def test_check_paths_recognizes_exists_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "exists").mkdir()

            result = check_runtime_env.check_paths(root, ["exists", "missing"])

        self.assertEqual(result["exists"]["status"], "exists")
        self.assertTrue(result["exists"]["exists"])
        self.assertEqual(result["missing"]["status"], "missing")
        self.assertFalse(result["missing"]["exists"])

    def test_build_report_contains_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = check_runtime_env.build_report(project_root=temp_dir)

        self.assertIn("python", result)
        self.assertIn("packages", result)
        self.assertIn("paths", result)
        self.assertIn("camera", result)
        self.assertIn("overall_status", result)

    def test_build_report_without_camera_marks_camera_unchecked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = check_runtime_env.build_report(project_root=temp_dir, check_camera_enabled=False)

        self.assertFalse(result["camera"]["checked"])

    def test_check_camera_uses_mock_cv2_without_real_camera(self) -> None:
        fake_cv2 = types.SimpleNamespace(VideoCapture=FakeVideoCapture)
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            result = check_runtime_env.check_camera(camera_index=1)

        self.assertTrue(result["checked"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["camera_index"], 1)
        self.assertEqual(result["width"], 640)
        self.assertEqual(result["height"], 480)

    def test_main_can_be_called_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = check_runtime_env.main(["--project-root", temp_dir, "--json"])

        self.assertEqual(exit_code, 0)
        self.assertIn("overall_status", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
