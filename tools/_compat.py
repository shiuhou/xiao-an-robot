"""Compatibility helpers for root-level tool wrappers."""

from __future__ import annotations

import importlib
import runpy
import sys
from collections.abc import MutableMapping


def reexport(module_name: str, namespace: MutableMapping[str, object]) -> None:
    module = importlib.import_module(module_name)
    public = getattr(module, "__all__", None)
    if public is None:
        public = [name for name in vars(module) if not name.startswith("_")]
    for name in public:
        namespace[name] = getattr(module, name)
    namespace["__doc__"] = module.__doc__


def run_module(module_name: str) -> None:
    runpy.run_module(module_name, run_name="__main__")


def alias_module(module_name: str, alias: str) -> None:
    sys.modules[alias] = importlib.import_module(module_name)
