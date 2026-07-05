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

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "text": self.text,
            "source": self.source,
            "session_id": self.session_id,
            "context": self.context if isinstance(self.context, dict) else {},
        }


@dataclass
class OpenClawToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "arguments": self.arguments if isinstance(self.arguments, dict) else {},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OpenClawToolCall":
        if not isinstance(data, dict):
            return cls(name="")
        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        return cls(
            name=data.get("name", ""),
            arguments=arguments,
        )


@dataclass
class OpenClawDecision:
    handled: bool
    display_text: str = ""
    spoken_text: str = ""
    reply_text: str = ""
    suppress_auto_tts: bool = False
    tool_calls: list[OpenClawToolCall] = field(default_factory=list)
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return {
            "handled": self.handled,
            "display_text": self.display_text,
            "spoken_text": self.spoken_text,
            "reply_text": self.reply_text,
            "suppress_auto_tts": self.suppress_auto_tts,
            "tool_calls": [tool_call.to_dict() for tool_call in self.tool_calls],
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OpenClawDecision":
        if not isinstance(data, dict):
            return cls(handled=False)

        tool_calls_data = data.get("tool_calls", [])
        if not isinstance(tool_calls_data, list):
            tool_calls_data = []

        reply_text = data.get("reply_text", "")
        if not isinstance(reply_text, str):
            reply_text = ""
        display_text = data.get("display_text", "")
        if not isinstance(display_text, str):
            display_text = ""
        spoken_text = data.get("spoken_text", "")
        if not isinstance(spoken_text, str):
            spoken_text = ""

        return cls(
            handled=bool(data.get("handled", False)),
            display_text=display_text,
            spoken_text=spoken_text,
            reply_text=reply_text,
            suppress_auto_tts=data.get("suppress_auto_tts") is True,
            tool_calls=[OpenClawToolCall.from_dict(item) for item in tool_calls_data],
            raw=data,
        )


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
