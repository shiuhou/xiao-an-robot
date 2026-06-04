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

    def __init__(self, model_path: str, device: str = "CPU"):
        Core = self._load_openvino_core()

        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenVINO model path does not exist: {model_path}")

        self.model_path = str(path)
        self.device = device
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

    def predict(self, frame: dict) -> dict:
        raise NotImplementedError("OpenVINO inference postprocessing is not implemented yet.")
