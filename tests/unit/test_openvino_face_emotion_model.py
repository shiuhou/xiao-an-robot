"""Unit tests for OpenVINOFaceEmotionModel placeholder."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from base_station.perception.openvino_face_emotion_model import OpenVINOFaceEmotionModel


class FakeCompiledModel:
    inputs = ["input_layer"]
    outputs = ["output_layer"]


class FakeCore:
    instances: list["FakeCore"] = []
    compile_error: Exception | None = None

    def __init__(self) -> None:
        self.read_model = Mock(return_value="fake_model")
        self.compile_model = Mock(side_effect=self._compile_model)
        FakeCore.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.compile_error = None

    def _compile_model(self, model: object, device: str) -> FakeCompiledModel:
        if FakeCore.compile_error is not None:
            raise FakeCore.compile_error
        return FakeCompiledModel()


def openvino_runtime_modules() -> dict:
    FakeCore.reset()
    openvino = types.ModuleType("openvino")
    runtime = types.ModuleType("openvino.runtime")
    runtime.Core = FakeCore
    openvino.runtime = runtime
    return {
        "openvino": openvino,
        "openvino.runtime": runtime,
    }


def openvino_top_level_modules() -> dict:
    FakeCore.reset()
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

    def test_openvino_runtime_core_initializes_and_compiles_model(self) -> None:
        modules = openvino_runtime_modules()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "emotion.xml"
            model_path.write_text("<xml />", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                model = OpenVINOFaceEmotionModel(str(model_path), device="GPU")

        self.assertEqual(model.model_path, str(model_path))
        self.assertEqual(model.device, "GPU")
        self.assertIs(model.core, FakeCore.instances[0])
        self.assertEqual(model.model, "fake_model")
        self.assertIsInstance(model.compiled_model, FakeCompiledModel)
        self.assertEqual(model.input_layer, "input_layer")
        self.assertEqual(model.output_layer, "output_layer")
        model.core.read_model.assert_called_once_with(str(model_path))
        model.core.compile_model.assert_called_once_with("fake_model", "GPU")

    def test_top_level_openvino_core_initializes_model(self) -> None:
        modules = openvino_top_level_modules()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "emotion.xml"
            model_path.write_text("<xml />", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                model = OpenVINOFaceEmotionModel(str(model_path))

        self.assertEqual(model.model_path, str(model_path))
        self.assertEqual(model.device, "CPU")
        model.core.read_model.assert_called_once_with(str(model_path))
        model.core.compile_model.assert_called_once_with("fake_model", "CPU")

    def test_predict_raises_not_implemented(self) -> None:
        modules = openvino_runtime_modules()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "emotion.xml"
            model_path.write_text("<xml />", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                model = OpenVINOFaceEmotionModel(str(model_path))

        with self.assertRaisesRegex(NotImplementedError, "OpenVINO inference postprocessing is not implemented yet"):
            model.predict({"frame_id": 1})

    def test_compile_model_error_is_not_swallowed(self) -> None:
        modules = openvino_runtime_modules()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "emotion.xml"
            model_path.write_text("<xml />", encoding="utf-8")
            FakeCore.compile_error = RuntimeError("compile failed")

            with patch.dict(sys.modules, modules):
                with self.assertRaisesRegex(RuntimeError, "compile failed"):
                    OpenVINOFaceEmotionModel(str(model_path))


if __name__ == "__main__":
    unittest.main()
