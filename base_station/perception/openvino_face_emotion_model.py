"""OpenVINO face emotion model initialization layer.

This module loads and compiles an OpenVINO model, but real image preprocessing,
inference execution, and postprocessing are intentionally left for a later
stage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class OpenVINOFaceEmotionModel:
    """OpenVINO-backed face emotion model shell."""

    def __init__(
        self,
        model_path: str,
        device: str = "CPU",
        input_size: tuple[int, int] = (224, 224),
        normalize: bool = True,
        bgr_to_rgb: bool = True,
    ):
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenVINO model path does not exist: {model_path}")

        Core = self._load_openvino_core()

        self.model_path = str(path)
        self.device = device
        self.input_size = input_size
        self.normalize = normalize
        self.bgr_to_rgb = bgr_to_rgb
        self.core = Core()
        self.model = self.core.read_model(self.model_path)
        self.compiled_model = self.core.compile_model(self.model, self.device)
        self.inputs = list(getattr(self.compiled_model, "inputs", []) or [])
        self.outputs = list(getattr(self.compiled_model, "outputs", []) or [])
        self.input_layer = self.inputs[0] if self.inputs else None
        self.output_layer = self.outputs[0] if self.outputs else None

    @staticmethod
    def _load_openvino_core() -> Any:
        try:
            try:
                from openvino.runtime import Core
            except ImportError:
                from openvino import Core
        except ImportError as exc:
            raise ImportError(
                "OpenVINO is not installed. Install openvino to use OpenVINOFaceEmotionModel."
            ) from exc
        return Core

    def preprocess(self, frame: dict):
        if "payload" not in frame or frame["payload"] is None:
            raise ValueError("OpenVINOFaceEmotionModel.preprocess requires frame['payload'] image data.")

        try:
            import numpy as np
        except ImportError as exc:
            raise ImportError("numpy is required to preprocess OpenVINO face emotion frames.") from exc

        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError("opencv-python is required to preprocess OpenVINO face emotion frames.") from exc

        image = frame["payload"]
        if not isinstance(image, np.ndarray):
            image = np.asarray(image)

        input_height, input_width = self.input_size
        image = cv2.resize(image, (input_width, input_height))
        if self.bgr_to_rgb:
            image = image[:, :, ::-1]

        image = image.astype(np.float32)
        if self.normalize:
            image = image / 255.0

        return image.transpose(2, 0, 1)[None, ...]

    def infer(self, input_tensor):
        return self.compiled_model(input_tensor)

    def postprocess(self, outputs) -> dict:
        raise NotImplementedError("OpenVINO inference postprocessing is not implemented yet.")

    def predict(self, frame: dict) -> dict:
        input_tensor = self.preprocess(frame)
        outputs = self.infer(input_tensor)
        return self.postprocess(outputs)
