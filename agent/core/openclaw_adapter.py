"""OpenClaw adapter protocol for Xiao An runtime integration.

OpenClaw is intended to be Xiao An's main brain. The local agent/core layer
should stay focused on runtime orchestration and hardware execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class OpenClawEvent:
    type: str
    text: str | None = None
    source: str = "unknown"
    session_id: str = "default"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenClawToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenClawDecision:
    handled: bool
    reply_text: str = ""
    tool_calls: list[OpenClawToolCall] = field(default_factory=list)
    raw: dict[str, Any] | None = None


class OpenClawAdapter(Protocol):
    """Synchronous adapter boundary for future OpenClaw runtime calls."""

    def handle_event(self, event: OpenClawEvent) -> OpenClawDecision:
        ...


class FakeOpenClawAdapter:
    """Minimal fake adapter for tests and local wiring checks."""

    def __init__(self, decision: OpenClawDecision | None = None):
        self.decision = decision or OpenClawDecision(
            handled=True,
            reply_text="收到，我会交给 OpenClaw 处理。",
        )
        self.events: list[OpenClawEvent] = []

    def handle_event(self, event: OpenClawEvent) -> OpenClawDecision:
        self.events.append(event)
        return self.decision
