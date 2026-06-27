"""Unit tests for the Qwen OpenVINO static-image probe tool."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def write_test_png(path: Path) -> None:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:
        raise unittest.SkipTest(f"OpenCV/numpy not available for image fixture: {exc}") from exc

    image = np.zeros((1, 1, 3), dtype=np.uint8)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"failed to write test image: {path}")


class ProbeQwenVLOpenVINOTest(unittest.TestCase):
    def test_fake_output_mode_emits_raw_and_parsed_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.png"
            write_test_png(image_path)

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/probe_qwen_vl_openvino.py",
                    "--image-path",
                    str(image_path),
                    "--fake-output",
                    "tired",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["fake_output"], "tired")
        self.assertIn("raw_output", payload)
        self.assertEqual(payload["emotion_sample"]["emotion_tag"], "tired")
        self.assertEqual(payload["emotion_sample"]["frame_source"], "image_file")


if __name__ == "__main__":
    unittest.main()
