"""Thin OpenVINO IR runner for the OpenFace models (in-process inference).

Designed so the module imports WITHOUT openvino installed: ``import openvino``
and ``numpy`` are deferred into methods. This lets the pre/post logic be unit
tested with an injected fake compiled model (no real IR / no openvino needed).

Usage (production, in conda 'openface' env):
    runner = OVModelRunner("models_ov/star/star.xml", device="NPU")
    outputs = runner.infer(np_input)   # list[np.ndarray], in graph-output order
"""

from __future__ import annotations

from typing import Any


class OVModelRunner:
    def __init__(self, xml_path: str, device: str = "CPU", compiled_model: Any = None):
        """compiled_model: optional pre-compiled model (or fake) for injection/tests.
        When None, the IR is read+compiled lazily on first infer()."""
        self.xml_path = str(xml_path)
        self.device = device
        self._compiled = compiled_model

    def _ensure_compiled(self):
        if self._compiled is None:
            import openvino as ov  # deferred: keep module importable without openvino

            core = ov.Core()
            model = core.read_model(self.xml_path)
            self._compiled = core.compile_model(model, self.device)
        return self._compiled

    @staticmethod
    def _as_input(x):
        import numpy as np

        arr = np.asarray(x, dtype=np.float32)
        return np.ascontiguousarray(arr)

    def infer(self, x) -> list:
        """Run inference and return outputs as a list of np.ndarray, in the
        compiled model's output-port order."""
        import numpy as np

        compiled = self._ensure_compiled()
        result = compiled(self._as_input(x))
        return [np.asarray(result[port]) for port in compiled.outputs]
