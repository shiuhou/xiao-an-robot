"""Unit tests for OpenVINOFaceEmotionModel placeholder."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from base_station.perception.openvino_face_emotion_model import OpenVINOFaceEmotionModel

try:
    import numpy as np
except ImportError:
    np = None


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


def fake_cv2_module() -> types.ModuleType:
    cv2 = types.ModuleType("cv2")

    def resize(image, size):
        if np is None:
            raise RuntimeError("numpy unavailable")
        width, height = size
        return np.resize(image, (height, width, image.shape[2]))

    cv2.resize = resize
    return cv2


class OpenVINOFaceEmotionModelTest(unittest.TestCase):
    def create_model(
        self,
        input_size: tuple[int, int] = (224, 224),
        normalize: bool = True,
        bgr_to_rgb: bool = True,
    ) -> OpenVINOFaceEmotionModel:
        modules = openvino_runtime_modules()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "emotion.xml"
            model_path.write_text("<xml />", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                return OpenVINOFaceEmotionModel(
                    str(model_path),
                    input_size=input_size,
                    normalize=normalize,
                    bgr_to_rgb=bgr_to_rgb,
                )

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

    def test_preprocess_missing_payload_raises_value_error(self) -> None:
        model = self.create_model()

        with self.assertRaisesRegex(ValueError, "payload"):
            model.preprocess({"frame_id": 1})

    @unittest.skipIf(np is None, "numpy is not installed")
    def test_preprocess_converts_hwc_to_nchw(self) -> None:
        model = self.create_model(input_size=(2, 2), normalize=False, bgr_to_rgb=False)
        image = np.zeros((2, 2, 3), dtype=np.uint8)

        with patch.dict(sys.modules, {"cv2": fake_cv2_module()}):
            output = model.preprocess({"payload": image})

        self.assertEqual(output.shape, (1, 3, 2, 2))

    @unittest.skipIf(np is None, "numpy is not installed")
    def test_preprocess_normalizes_float32_values(self) -> None:
        model = self.create_model(input_size=(1, 1), normalize=True, bgr_to_rgb=False)
        image = np.array([[[255, 128, 0]]], dtype=np.uint8)

        with patch.dict(sys.modules, {"cv2": fake_cv2_module()}):
            output = model.preprocess({"payload": image})

        self.assertEqual(output.dtype, np.float32)
        self.assertGreaterEqual(float(output.min()), 0.0)
        self.assertLessEqual(float(output.max()), 1.0)
        self.assertEqual(float(output[0, 0, 0, 0]), 1.0)

    @unittest.skipIf(np is None, "numpy is not installed")
    def test_preprocess_converts_bgr_to_rgb(self) -> None:
        model = self.create_model(input_size=(1, 1), normalize=False, bgr_to_rgb=True)
        image = np.array([[[10, 20, 30]]], dtype=np.uint8)

        with patch.dict(sys.modules, {"cv2": fake_cv2_module()}):
            output = model.preprocess({"payload": image})

        self.assertEqual(output[0, 0, 0, 0], 30)
        self.assertEqual(output[0, 1, 0, 0], 20)
        self.assertEqual(output[0, 2, 0, 0], 10)

    @unittest.skipIf(np is None, "numpy is not installed")
    def test_preprocess_input_size_controls_output_shape(self) -> None:
        model = self.create_model(input_size=(64, 64), normalize=False, bgr_to_rgb=False)
        image = np.zeros((2, 2, 3), dtype=np.uint8)

        with patch.dict(sys.modules, {"cv2": fake_cv2_module()}):
            output = model.preprocess({"payload": image})

        self.assertEqual(output.shape, (1, 3, 64, 64))

    @unittest.skipIf(np is None, "numpy is not installed")
    def test_preprocess_missing_cv2_raises_import_error(self) -> None:
        model = self.create_model()
        image = np.zeros((2, 2, 3), dtype=np.uint8)

        with patch.dict(sys.modules, {"cv2": None}):
            with self.assertRaisesRegex(ImportError, "opencv-python"):
                model.preprocess({"payload": image})

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
