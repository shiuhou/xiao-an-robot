"""Factory helpers for selecting an OpenClaw adapter from environment."""

from __future__ import annotations

import os
from collections.abc import Mapping

from agent.core.http_openclaw_adapter import HttpOpenClawAdapter
from agent.core.openclaw_adapter import FakeOpenClawAdapter


DEFAULT_OPENCLAW_BACKEND = "fake"
DEFAULT_OPENCLAW_URL = "http://127.0.0.1:8766"
DEFAULT_OPENCLAW_ENDPOINT = "/events"
DEFAULT_OPENCLAW_TIMEOUT_SEC = 5.0


def _parse_timeout(value: str | None) -> float:
    if value is None:
        return DEFAULT_OPENCLAW_TIMEOUT_SEC
    try:
        return float(value)
    except (TypeError, ValueError):
        return DEFAULT_OPENCLAW_TIMEOUT_SEC


def build_openclaw_adapter_from_env(environ: Mapping[str, str] | None = None):
    active_environ = os.environ if environ is None else environ
    backend = active_environ.get("XIAO_AN_OPENCLAW_BACKEND", DEFAULT_OPENCLAW_BACKEND).strip().lower()

    if backend == "fake":
        return FakeOpenClawAdapter()

    if backend == "http":
        return HttpOpenClawAdapter(
            base_url=active_environ.get("XIAO_AN_OPENCLAW_URL", DEFAULT_OPENCLAW_URL),
            endpoint=active_environ.get("XIAO_AN_OPENCLAW_ENDPOINT", DEFAULT_OPENCLAW_ENDPOINT),
            timeout_sec=_parse_timeout(active_environ.get("XIAO_AN_OPENCLAW_TIMEOUT_SEC")),
        )

    raise ValueError(f"Unknown OpenClaw backend: {backend}")
