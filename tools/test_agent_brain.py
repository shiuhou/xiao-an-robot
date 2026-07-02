#!/usr/bin/env python3
"""Compatibility wrapper for `tools.legacy.manual_agent_brain_smoke`."""

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools._compat import alias_module, run_module

_TARGET = "tools.legacy.manual_agent_brain_smoke"
if __name__ == "__main__":
    run_module(_TARGET)
else:
    alias_module(_TARGET, __name__)
