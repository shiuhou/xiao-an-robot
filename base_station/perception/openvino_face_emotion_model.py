"""OpenVINO face emotion model placeholder.

This module only validates configuration and OpenVINO availability. Real model
compilation and inference are intentionally left for a later stage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class OpenVINOFaceEmotionModel:
    """Placeholder for a future OpenVINO-backed face emotion model."""

    def __init__(self, model_path: str, device: str = "CPU"):
        self._load_openvino_core()

        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenVINO model path does not exist: {model_path}")

        self.model_path = str(path)
        self.device = device

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
        raise NotImplementedError("OpenVINO inference is not implemented yet.")
