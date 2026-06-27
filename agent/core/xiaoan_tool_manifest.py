"""OpenClaw-facing Xiao An robot body tool manifest."""

from __future__ import annotations

from typing import Any


XIAOAN_TOOL_MANIFEST: list[dict[str, Any]] = [
    {
        "name": "xiaoan.robot.say",
        "purpose": "Speak a short sentence through the robot TTS path.",
        "parameters": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Short text for Xiao An to say.",
                },
            },
        },
        "returns": {
            "ok": "boolean",
            "tool": "xiaoan.robot.say",
            "result": "Robot gateway acknowledgement.",
        },
        "failure": {
            "ok": False,
            "error": "missing_text | robot_gateway_error",
        },
    },
    {
        "name": "xiaoan.robot.expression",
        "purpose": "Show a named facial expression on the robot display.",
        "parameters": {
            "type": "object",
            "required": ["expression"],
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Expression name such as neutral, happy, caring, calm.",
                },
                "duration_ms": {
                    "type": "integer",
                    "description": "Optional display duration in milliseconds.",
                },
                "loop": {
                    "type": "boolean",
                    "description": "Whether the expression animation should loop.",
                },
            },
        },
        "returns": {
            "ok": "boolean",
            "tool": "xiaoan.robot.expression",
            "result": "Robot gateway acknowledgement.",
        },
        "failure": {
            "ok": False,
            "error": "missing_expression | robot_gateway_error",
        },
    },
    {
        "name": "xiaoan.robot.move_out",
        "purpose": "Move Xiao An a short safe distance out of the dock.",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "speed": {
                    "type": "number",
                    "description": "Optional motion speed, clamped to <= 0.2 for local software safety.",
                },
                "distance_cm": {
                    "type": "number",
                    "description": "Optional travel distance, clamped to <= 2 cm for local software safety.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Optional motion timeout, clamped to <= 500 ms for local software safety.",
                },
            },
        },
        "returns": {
            "ok": "boolean",
            "tool": "xiaoan.robot.move_out",
            "result": "Robot gateway acknowledgement.",
        },
        "failure": {
            "ok": False,
            "error": "robot_gateway_error",
        },
    },
    {
        "name": "xiaoan.robot.return_to_dock",
        "purpose": "Return Xiao An to the dock through the robot motion path.",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "speed": {
                    "type": "number",
                    "description": "Optional motion speed, clamped to <= 0.2 for local software safety.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Optional motion timeout, clamped to <= 500 ms for local software safety.",
                },
            },
        },
        "returns": {
            "ok": "boolean",
            "tool": "xiaoan.robot.return_to_dock",
            "result": "Robot gateway acknowledgement.",
        },
        "failure": {
            "ok": False,
            "error": "robot_gateway_error",
        },
    },
    {
        "name": "xiaoan.robot.care",
        "purpose": "Run Xiao An's local active-care sequence.",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Optional short care message to speak.",
                },
                "reply_text": {
                    "type": "string",
                    "description": "Optional decision reply text associated with this care action.",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason code for the care action.",
                },
                "speed": {
                    "type": "number",
                    "description": "Optional motion speed, clamped to <= 0.2 for local software safety.",
                },
                "distance_cm": {
                    "type": "number",
                    "description": "Optional travel distance, clamped to <= 2 cm for local software safety.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Optional motion timeout, clamped to <= 500 ms for local software safety.",
                },
            },
        },
        "returns": {
            "ok": "boolean",
            "tool": "xiaoan.robot.care",
            "actions": "List of robot gateway acknowledgements.",
        },
        "failure": {
            "ok": False,
            "error": "robot_gateway_error",
        },
    },
    {
        "name": "xiaoan.breathing.start",
        "purpose": "Start a short local breathing-guide interaction.",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Optional opening guidance text.",
                },
            },
        },
        "returns": {
            "ok": "boolean",
            "tool": "xiaoan.breathing.start",
            "actions": "List of expression and speech acknowledgements.",
        },
        "failure": {
            "ok": False,
            "error": "robot_gateway_error",
        },
    },
    {
        "name": "xiaoan.emotion.snapshot",
        "purpose": "Read the latest local emotion summary from the Local Event Store.",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "seconds": {
                    "type": "integer",
                    "description": "Lookback window in seconds. Default: 300.",
                },
            },
        },
        "returns": {
            "ok": "boolean",
            "tool": "xiaoan.emotion.snapshot",
            "snapshot": "Recent emotion summary.",
        },
        "failure": {
            "ok": False,
            "error": "emotion_store_unavailable",
        },
    },
    {
        "name": "xiaoan.runtime.status",
        "purpose": "Read local Xiao An runtime status and ownership boundary.",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {},
        },
        "returns": {
            "ok": "boolean",
            "tool": "xiaoan.runtime.status",
            "status": "Runtime status object.",
        },
        "failure": {
            "ok": False,
            "error": "runtime_status_unavailable",
        },
    },
]

XIAOAN_TOOL_NAMES = {
    item["name"]
    for item in XIAOAN_TOOL_MANIFEST
}


def tool_manifest() -> list[dict[str, Any]]:
    """Return a copy of the OpenClaw-facing Xiao An tool manifest."""

    return [dict(item) for item in XIAOAN_TOOL_MANIFEST]
