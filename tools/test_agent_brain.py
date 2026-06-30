#!/usr/bin/env python3
"""Compatibility wrapper for `tools.legacy.test_agent_brain`."""

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools._compat import alias_module, run_module

_TARGET = "tools.legacy.test_agent_brain"
if __name__ == "__main__":
    run_module(_TARGET)
else:
    alias_module(_TARGET, __name__)