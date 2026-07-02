#!/usr/bin/env python3
"""Compatibility wrapper for `scripts.debug.try_vlm_once`."""

from pathlib import Path
import importlib
import runpy
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TARGET = "scripts.debug.try_vlm_once"
if __name__ == "__main__":
    runpy.run_module(_TARGET, run_name="__main__")
else:
    sys.modules[__name__] = importlib.import_module(_TARGET)