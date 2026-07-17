"""Lightweight routing hints for Xiao An OpenClaw bridge events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CAPTURE_SCHEMA_VERSION = "xiaoan.assistant_capture_context.v1"
CAPTURE_DEMO_INTENT = "assistant_capture"

TOOL_PROFILE_NONE = "none"
TOOL_PROFILE_WORK_CAPTURE = "work_capture"
TOOL_PROFILE_CONVERSATION = "conversation"
TOOL_PROFILE_ROBOT_ACTION = "robot_action"
TOOL_PROFILE_COMPANION = "companion"
TOOL_PROFILE_EMOTION = "emotion"
TOOL_PROFILE_DEFAULT = "default"


@dataclass(frozen=True)
class RouteHint:
    kind: str
    tool_profile: str
    intent_hint: str = "conversation"
    capture_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind,
            "tool_profile": self.tool_profile,
            "intent_hint": self.intent_hint,
        }
        if self.capture_kind is not None:
            data["capture_kind"] = self.capture_kind
        return data


def route_asr_text(text: str | None) -> RouteHint:
    """Classify a terminal ASR transcript into a minimal OpenClaw route hint."""

    normalized = (text or "").strip().lower()
    if not normalized:
        return RouteHint(
            kind="conversation",
            tool_profile=TOOL_PROFILE_CONVERSATION,
            intent_hint="empty",
        )

    capture_kind = _capture_kind(normalized)
    if capture_kind is not None:
        return RouteHint(
            kind="work_capture",
            tool_profile=TOOL_PROFILE_WORK_CAPTURE,
            intent_hint=capture_kind,
            capture_kind=capture_kind,
        )

    if _looks_like_robot_action(normalized):
        return RouteHint(
            kind="robot_action",
            tool_profile=TOOL_PROFILE_ROBOT_ACTION,
            intent_hint="robot_action",
        )

    return RouteHint(
        kind="conversation",
        tool_profile=TOOL_PROFILE_CONVERSATION,
        intent_hint="conversation",
    )


def compact_asr_payload(payload: dict[str, Any], route_hint: RouteHint) -> dict[str, Any]:
    """Keep only semantic fields needed by OpenClaw; leave audio/VAD data local."""

    compact: dict[str, Any] = {
        "text": _text(payload.get("text")),
    }
    for key in ("source", "session_id", "timestamp_ms"):
        if key in payload:
            compact[key] = payload[key]
    if "disable_companion_fast_path" in payload:
        compact["disable_companion_fast_path"] = bool(payload.get("disable_companion_fast_path"))
    if route_hint.capture_kind is not None:
        compact["capture_kind"] = route_hint.capture_kind
    return compact


def openclaw_base_context_for_asr(payload: dict[str, Any], companion_result: dict[str, Any]) -> dict[str, Any]:
    route_hint = route_asr_text(_text(payload.get("text")))
    compact_payload = compact_asr_payload(payload, route_hint)
    context: dict[str, Any] = {
        "payload": compact_payload,
        "companion_result": companion_result,
        "route_hint": route_hint.to_dict(),
        "tool_profile": route_hint.tool_profile,
        "intent_hint": route_hint.intent_hint,
    }
    if route_hint.kind == "work_capture":
        context["schema_version"] = CAPTURE_SCHEMA_VERSION
        context["demo_intent"] = CAPTURE_DEMO_INTENT
        context["capture_kind_hint"] = route_hint.capture_kind
    return context


def tool_names_for_profile(profile: str | None) -> list[str] | None:
    """Return an allowlist for a tool profile; None means use the full default."""

    if profile in {TOOL_PROFILE_NONE, TOOL_PROFILE_WORK_CAPTURE, TOOL_PROFILE_CONVERSATION}:
        return []
    if profile == TOOL_PROFILE_COMPANION:
        return [
            "xiaoan.robot.say",
            "xiaoan.robot.expression",
            "xiaoan.robot.care",
        ]
    if profile == TOOL_PROFILE_EMOTION:
        return [
            "xiaoan.robot.say",
            "xiaoan.robot.expression",
            "xiaoan.robot.care",
            "xiaoan.emotion.snapshot",
        ]
    if profile == TOOL_PROFILE_ROBOT_ACTION:
        return [
            "xiaoan.robot.say",
            "xiaoan.robot.expression",
            "xiaoan.robot.move_out",
            "xiaoan.robot.return_to_dock",
            "xiaoan.robot.turn",
            "xiaoan.robot.care",
            "xiaoan.breathing.start",
            "xiaoan.runtime.status",
        ]
    return None


def _capture_kind(text: str) -> str | None:
    if any(keyword in text for keyword in ("想法", "点子", "灵感")):
        return "idea"
    if any(keyword in text for keyword in ("任务", "待办", "todo", "to-do")):
        return "task"
    if any(keyword in text for keyword in ("提醒我", "到点提醒", "待会提醒", "分钟后提醒", "小时后提醒")):
        return "reminder"
    if any(keyword in text for keyword in ("会议", "开会", "meeting")):
        return "meeting"
    if any(keyword in text for keyword in ("记一下", "存一下", "记录", "记到", "写下来")):
        return "note"
    if any(keyword in text for keyword in ("加入日程", "加到日程", "添加日程", "日程")):
        return "meeting"
    return None


def _looks_like_robot_action(text: str) -> bool:
    return any(
        keyword in text
        for keyword in (
            "笑一个",
            "表情",
            "出来",
            "陪我",
            "安慰我",
            "动一下",
            "转一下",
            "回 dock",
            "回dock",
            "回去",
            "归位",
            "呼吸练习",
        )
    )


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
