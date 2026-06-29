"""Unit tests for OpenFace OV adapter frame-boundary behavior."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from base_station.perception import openface_ov_adapter as adapter


class OpenFaceOVAdapterTest(unittest.TestCase):
    def test_perceive_callable_unwraps_frame_payload_before_openface_runtime(self) -> None:
        calls = []

        def build_ov_perceive(models_dir: str, device: str):
            calls.append({"models_dir": models_dir, "device": device})

            def raw_perceive(image):
                calls.append({"image": image})
                return {"face_confidence": 0.9}

            return raw_perceive

        fake_module = types.ModuleType("ov_perceive")
        fake_module.build_ov_perceive = build_ov_perceive
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as models_dir:
            runtime_dir = Path(root_dir) / "runtime"
            runtime_dir.mkdir()
            image = object()
            with patch.object(adapter, "DEFAULT_RUNTIME_DIR", runtime_dir), patch.dict(
                sys.modules,
                {"ov_perceive": fake_module},
            ):
                perceive = adapter.build_ov_perceive_callable(
                    models_dir=models_dir,
                    device="CPU",
                )

            result = perceive({"payload": image, "frame_id": 1})

        self.assertEqual(result, {"face_confidence": 0.9})
        self.assertEqual(calls[0]["device"], "CPU")
        self.assertIs(calls[1]["image"], image)


if __name__ == "__main__":
    unittest.main()
