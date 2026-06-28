"""Fake work activity samples for local context-memory development."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class WorkActivitySample:
    timestamp_ms: int
    source: str
    app_name: str
    window_title: str
    activity_type: str
    project_hint: str | None
    confidence: float
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "source": self.source,
            "app_name": self.app_name,
            "window_title": self.window_title,
            "activity_type": self.activity_type,
            "project_hint": self.project_hint,
            "confidence": self.confidence,
            "duration_seconds": self.duration_seconds,
        }


class WorkActivitySource:
    """Interface for work activity sample sources."""

    def next_sample(self) -> WorkActivitySample:
        raise NotImplementedError


PATTERN_SAMPLES = {
    "coding": {
        "app_name": "VS Code",
        "window_title": "xiao-an-robot - memory.py",
        "activity_type": "coding",
        "project_hint": "xiao-an-robot",
        "confidence": 0.85,
    },
    "writing": {
        "app_name": "Word",
        "window_title": "项目设计方案书",
        "activity_type": "writing",
        "project_hint": "xiao-an-robot",
        "confidence": 0.8,
    },
    "browsing": {
        "app_name": "Chrome",
        "window_title": "OpenVINO documentation",
        "activity_type": "browsing",
        "project_hint": "xiao-an-robot",
        "confidence": 0.75,
    },
    "meeting": {
        "app_name": "Tencent Meeting",
        "window_title": "项目讨论会议",
        "activity_type": "meeting",
        "project_hint": "xiao-an-robot",
        "confidence": 0.8,
    },
    "idle": {
        "app_name": "Desktop",
        "window_title": "idle",
        "activity_type": "idle",
        "project_hint": None,
        "confidence": 0.6,
    },
    "unknown": {
        "app_name": "Unknown",
        "window_title": "unknown",
        "activity_type": "unknown",
        "project_hint": None,
        "confidence": 0.0,
    },
}


class FakeWorkActivitySource(WorkActivitySource):
    """Generate deterministic fake work activity samples."""

    def __init__(self, pattern: str = "coding", duration_seconds: float | None = None):
        if pattern not in PATTERN_SAMPLES:
            supported = ", ".join(sorted(PATTERN_SAMPLES))
            raise ValueError(f"Unsupported fake work activity pattern: {pattern}. Supported: {supported}.")
        self.pattern = pattern
        self.duration_seconds = duration_seconds

    def next_sample(self) -> WorkActivitySample:
        sample = PATTERN_SAMPLES[self.pattern]
        return WorkActivitySample(
            timestamp_ms=int(time.time() * 1000),
            source="fake_work_activity",
            app_name=str(sample["app_name"]),
            window_title=str(sample["window_title"]),
            activity_type=str(sample["activity_type"]),
            project_hint=sample["project_hint"],
            confidence=float(sample["confidence"]),
            duration_seconds=self.duration_seconds,
        )
