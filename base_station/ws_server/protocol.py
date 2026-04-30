"""
protocol.py
-----------
Python dataclass definitions for all WebSocket messages.
Matches docs/protocol.md v0.1

Usage:
    from ws_server.protocol import MessageType, DeviceHello, SystemWelcome

Author: Team Xiao An
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from enum import Enum
import time


class MessageType(str, Enum):
    # Robot -> Base Station
    DEVICE_HELLO       = "device.hello"
    DEVICE_HEARTBEAT   = "device.heartbeat"
    SENSOR_BUTTON      = "sensor.button"
    SENSOR_DOCK_STATUS = "sensor.dock_status"
    MOTION_COMPLETED   = "motion.completed"
    ERROR_REPORT       = "error.report"

    # Base Station -> Robot
    SYSTEM_WELCOME     = "system.welcome"
    DISPLAY_EXPRESSION = "display.expression"
    MOTION_EXECUTE     = "motion.execute"
    AUDIO_PLAY_TTS     = "audio.play_tts"
    AUDIO_PLAY_LOCAL   = "audio.play_local"
    CONFIG_UPDATE      = "config.update"
    SYSTEM_SHUTDOWN    = "system.shutdown"


class Expression(str, Enum):
    HAPPY     = "happy"
    SAD       = "sad"
    CARING    = "caring"
    TIRED     = "tired"
    THINKING  = "thinking"
    SPEAKING  = "speaking"
    IDLE      = "idle"
    SURPRISED = "surprised"
    SLEEPING  = "sleeping"


class MotionAction(str, Enum):
    MOVE_OUT_OF_DOCK  = "move_out_of_dock"
    MOVE_BACK_TO_DOCK = "move_back_to_dock"
    TURN              = "turn"
    NOD_HEAD          = "nod_head"
    TILT_HEAD         = "tilt_head"
    WIGGLE_EARS       = "wiggle_ears"
    STOP              = "stop"


# ── Helpers ──────────────────────────────────────────────────────────────────

_seq_counter = 0

def next_seq() -> int:
    global _seq_counter
    _seq_counter += 1
    return _seq_counter

def build_message(msg_type: MessageType, payload: dict) -> dict:
    return {
        "type":    msg_type.value,
        "ts":      int(time.time() * 1000),
        "seq":     next_seq(),
        "payload": payload,
    }


# ── Outbound message builders (Base Station -> Robot) ────────────────────────

def make_welcome(session_id: str, video_fps: float = 0.2,
                 audio_sample_rate: int = 16000,
                 heartbeat_interval_sec: int = 10) -> dict:
    return build_message(MessageType.SYSTEM_WELCOME, {
        "session_id":  session_id,
        "server_time": int(time.time() * 1000),
        "config": {
            "video_fps":              video_fps,
            "audio_sample_rate":      audio_sample_rate,
            "heartbeat_interval_sec": heartbeat_interval_sec,
        }
    })

def make_expression(expression: Expression,
                    duration_ms: int = 0,
                    loop: bool = False) -> dict:
    return build_message(MessageType.DISPLAY_EXPRESSION, {
        "expression":  expression.value,
        "duration_ms": duration_ms,
        "loop":        loop,
    })

def make_motion(action_id: str, action: MotionAction,
                params: dict = None, timeout_ms: int = 5000) -> dict:
    return build_message(MessageType.MOTION_EXECUTE, {
        "action_id":  action_id,
        "action":     action.value,
        "params":     params or {},
        "timeout_ms": timeout_ms,
    })

def make_play_tts(audio_id: str, audio_url: str,
                  duration_ms: int, text_preview: str = "") -> dict:
    return build_message(MessageType.AUDIO_PLAY_TTS, {
        "audio_id":     audio_id,
        "audio_url":    audio_url,
        "duration_ms":  duration_ms,
        "text_preview": text_preview,
    })

def make_play_local(sound: str, volume: float = 0.8) -> dict:
    return build_message(MessageType.AUDIO_PLAY_LOCAL, {
        "sound":  sound,
        "volume": volume,
    })


# ── Inbound message parser (Robot -> Base Station) ───────────────────────────

def parse_message(raw: dict) -> tuple[MessageType, dict]:
    """
    Parse a raw dict from WebSocket into (MessageType, payload).
    Raises ValueError if type is unknown.
    """
    try:
        msg_type = MessageType(raw["type"])
    except (KeyError, ValueError):
        raise ValueError(f"Unknown message type: {raw.get('type')}")
    return msg_type, raw.get("payload", {})
