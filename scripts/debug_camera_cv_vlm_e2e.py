#!/usr/bin/env python3
"""Compatibility wrapper for `scripts.debug.debug_camera_cv_vlm_e2e`."""

from pathlib import Path
import importlib
import runpy
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TARGET = "scripts.debug.debug_camera_cv_vlm_e2e"
if __name__ == "__main__":
    runpy.run_module(_TARGET, run_name="__main__")
else:
    sys.modules[__name__] = importlib.import_module(_TARGET)