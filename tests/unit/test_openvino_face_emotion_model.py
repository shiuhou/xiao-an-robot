"""Unit tests for OpenVINOFaceEmotionModel placeholder."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from base_station.perception.openvino_face_emotion_model import OpenVINOFaceEmotionModel


class FakeCore:
    pass


def openvino_runtime_modules() -> dict:
    openvino = types.ModuleType("openvino")
    runtime = types.ModuleType("openvino.runtime")
    runtime.Core = FakeCore
    openvino.runtime = runtime
    return {
        "openvino": openvino,
        "openvino.runtime": runtime,
    }


def openvino_top_level_modules() -> dict:
    openvino = types.ModuleType("openvino")
    openvino.Core = FakeCore
    return {
        "openvino": openvino,
        "openvino.runtime": None,
    }


class OpenVINOFaceEmotionModelTest(unittest.TestCase):
    def test_missing_openvino_raises_clear_import_error(self) -> None:
        with patch.dict(sys.modules, {"openvino": None, "openvino.runtime": None}):
            with self.assertRaisesRegex(ImportError, "OpenVINO is not installed"):
                OpenVINOFaceEmotionModel("missing.xml")

    def test_missing_model_path_raises_file_not_found(self) -> None:
        modules = openvino_runtime_modules()
        missing_path = "missing_model.xml"

        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(FileNotFoundError, missing_path):
                OpenVINOFaceEmotionModel(missing_path)

    def test_can_create_model_when_openvino_runtime_and_model_path_exist(self) -> None:
        modules = openvino_runtime_modules()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "emotion.xml"
            model_path.write_text("<xml />", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                model = OpenVINOFaceEmotionModel(str(model_path), device="GPU")

        self.assertEqual(model.model_path, str(model_path))
        self.assertEqual(model.device, "GPU")

    def test_can_create_model_with_top_level_openvino_core(self) -> None:
        modules = openvino_top_level_modules()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "emotion.xml"
            model_path.write_text("<xml />", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                model = OpenVINOFaceEmotionModel(str(model_path))

        self.assertEqual(model.model_path, str(model_path))
        self.assertEqual(model.device, "CPU")

    def test_predict_raises_not_implemented(self) -> None:
        modules = openvino_runtime_modules()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "emotion.xml"
            model_path.write_text("<xml />", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                model = OpenVINOFaceEmotionModel(str(model_path))

        with self.assertRaisesRegex(NotImplementedError, "OpenVINO inference is not implemented yet"):
            model.predict({"frame_id": 1})


if __name__ == "__main__":
    unittest.main()
