#!/usr/bin/env python3
"""Demo 1: base-station USB mic -> ASR transcript -> local Agent screen."""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import struct
import sys
import threading
import time
from typing import Any
import warnings
import wave


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from base_station.monitor.asr_runtime import run_once as run_asr_once
from agent.core.action_executor import ActionExecutor
from agent.core.gateway import RobotGateway
from agent.core.gateway_openclaw_adapter import (
    DEFAULT_OPENCLAW_AGENT,
    DEFAULT_OPENCLAW_GATEWAY_TIMEOUT_SEC,
    DEFAULT_OPENCLAW_GATEWAY_URL,
    GatewayOpenClawAdapter,
)
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawEvent
from agent.core.xiaoan_tool_manifest import tool_manifest
from agent.skills.robot_motion import RobotMotionSkill


DEFAULT_RUNTIME_DIR = REPO_ROOT / "runtime"
DEFAULT_STATE_PATH = DEFAULT_RUNTIME_DIR / "demo1_transcript.json"
DEFAULT_TEXT_PATH = DEFAULT_RUNTIME_DIR / "demo1_transcript.txt"
DEFAULT_CONTEXT_PATH = DEFAULT_RUNTIME_DIR / "demo1_openclaw_context.json"
DEFAULT_PLAN_PATH = DEFAULT_RUNTIME_DIR / "demo1_action_plan.json"
DEFAULT_OPENCLAW_RESULT_PATH = DEFAULT_RUNTIME_DIR / "demo1_openclaw_result.json"
DEFAULT_LOG_PATH = DEFAULT_RUNTIME_DIR / "demo1_transcript.log.jsonl"
DEFAULT_AUDIO_DIR = DEFAULT_RUNTIME_DIR / "demo1_audio"
DEFAULT_SCREEN_URL = "http://127.0.0.1:8766"
DEMO_TITLE = "小安 Demo 1：基站麦克风语音识别"
OPENCLAW_CONTEXT_SCHEMA_VERSION = "demo1.openclaw_context.v1"
ACTION_PLAN_SCHEMA_VERSION = "demo1.action_plan.v1"
DEMO_INTENT = "care_companion"
CONTEXT_SOURCE = "base_station_mic"
ALLOWED_EXPRESSIONS = (
    "happy",
    "sad",
    "caring",
    "tired",
    "thinking",
    "speaking",
    "idle",
    "surprised",
    "sleeping",
)
ALLOWED_MOTIONS = ("forward", "backward", "left", "right", "stop", "move_out_of_dock")
ALLOWED_LOCAL_SOUNDS = ("care_01", "wake_01", "success_ding")
MOTION_GATEWAY_ALIASES = {
    "forward": "move_out_of_dock",
    "backward": "move_back_to_dock",
}
DEFAULT_TURN_ANGLE_DEG = 30.0
ASR_SAMPLE_RATE = 16000
ASR_CHANNELS = 1
ASR_SAMPLE_WIDTH = 2
TARGET_MAX_DBFS_MIN = -12.0
TARGET_MAX_DBFS_MAX = -6.0
EXPRESSION_REQUEST_KEYWORDS = ("表情", "表情包", "脸", "神情")
EXPRESSION_KEYWORD_RULES = (
    ("happy", "happy_expression_keyword", ("开心", "高兴", "快乐", "笑", "happy")),
    ("sad", "sad_expression_keyword", ("伤心", "难过", "悲伤", "sad")),
    ("caring", "caring_expression_keyword", ("关心", "关怀", "温柔", "安慰", "caring")),
    ("tired", "tired_expression_keyword", ("疲惫", "疲劳", "累", "困", "tired")),
    ("thinking", "thinking_expression_keyword", ("思考", "想", "thinking")),
    ("surprised", "surprised_expression_keyword", ("惊讶", "吃惊", "surprised")),
    ("sleeping", "sleeping_expression_keyword", ("睡觉", "睡眠", "sleeping")),
    ("idle", "idle_expression_keyword", ("普通", "默认", "idle")),
)
UNSUPPORTED_EXPRESSION_KEYWORDS = (
    "愤怒",
    "生气",
    "发怒",
    "怒",
    "angry",
    "calm",
    "neutral",
    "中性",
)


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def allowed_actions_spec() -> dict[str, Any]:
    return {
        "display.expression": {
            "expression": list(ALLOWED_EXPRESSIONS),
        },
        "motion.execute": {
            "action": list(ALLOWED_MOTIONS),
        },
        "audio.play_local": {
            "audio_id": list(ALLOWED_LOCAL_SOUNDS),
        },
        "audio.play_tts": {
            "mode": "mock_tone_only",
        },
    }


def openclaw_tool_contract() -> dict[str, Any]:
    return {
        "decision_owner": "openclaw_xiaoan_runtime",
        "allowed_tools": [
            "xiaoan.robot.expression",
            "xiaoan.robot.care",
            "xiaoan.robot.move_out",
            "xiaoan.robot.say",
        ],
        "allowed_expressions": list(ALLOWED_EXPRESSIONS),
        "notes": [
            "Demo 1 main path must let OpenClaw decide before local robot actions.",
            "Do not emit unsupported expressions; use allowed_expressions only.",
            "Unsupported expressions must fail validation instead of being silently remapped.",
        ],
    }


def demo1_openclaw_tool_manifest() -> list[dict[str, Any]]:
    allowed = set(openclaw_tool_contract()["allowed_tools"])
    ordered = list(openclaw_tool_contract()["allowed_tools"])
    by_name = {str(item.get("name") or ""): deepcopy(item) for item in tool_manifest()}
    filtered: list[dict[str, Any]] = []
    for name in ordered:
        if name not in allowed or name not in by_name:
            continue
        item = by_name[name]
        if name == "xiaoan.robot.expression":
            expression_spec = (
                item.get("parameters", {})
                .get("properties", {})
                .get("expression")
            )
            if isinstance(expression_spec, dict):
                expression_spec["enum"] = list(ALLOWED_EXPRESSIONS)
                expression_spec["description"] = (
                    "Allowed Demo 1 expression. One of: "
                    + ", ".join(ALLOWED_EXPRESSIONS)
                    + "."
                )
        filtered.append(item)
    return filtered


def build_no_decision_plan(route: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": ACTION_PLAN_SCHEMA_VERSION,
        "demo_intent": DEMO_INTENT,
        "timestamp": now_iso(),
        "route": route,
        "reason": reason,
        "handled": None,
        "allowed_actions": allowed_actions_spec(),
        "actions": [],
        "validation": {"ok": True, "errors": []},
    }


def build_state(
    *,
    status: str,
    transcript: str = "",
    source: str | None = None,
    audio_device: str | None = None,
    audio_device_index: int | str | None = None,
    audio_path: str | None = None,
    asr_backend: str | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "title": DEMO_TITLE,
        "status": status,
        "transcript": transcript,
        "source": source,
        "timestamp": now_iso(),
        "audio_device": audio_device,
        "audio_device_index": audio_device_index,
        "audio_path": audio_path,
        "asr_backend": asr_backend,
        "error": error,
        "details": details or {},
    }


def write_state(path: str | Path, state: dict[str, Any]) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def write_transcript_text(path: str | Path, transcript: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(transcript.strip() + "\n", encoding="utf-8")
    return target


def write_json_artifact(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def append_log(path: str | Path, state: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n")


def update_state(
    state_path: str | Path,
    log_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    state = build_state(**kwargs)
    write_state(state_path, state)
    append_log(log_path, state)
    return state


def load_state(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return build_state(status="idle")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return build_state(status="error", error=f"Failed to load demo state: {exc}")


def import_pyaudio():
    try:
        import pyaudio  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyAudio is required for USB microphone recording. "
            "Install base_station/requirements.txt, or use --mock-text for fallback."
        ) from exc
    return pyaudio


def _pyaudio_input_devices() -> list[dict[str, Any]]:
    pyaudio = import_pyaudio()
    audio = pyaudio.PyAudio()
    devices: list[dict[str, Any]] = []
    try:
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            if int(info.get("maxInputChannels") or 0) <= 0:
                continue
            devices.append(
                {
                    "backend": "pyaudio",
                    "index": int(info["index"]),
                    "device_id": str(info["index"]),
                    "name": str(info.get("name") or f"input-{index}"),
                    "max_input_channels": int(info.get("maxInputChannels") or 0),
                    "default_sample_rate": float(info.get("defaultSampleRate") or 0),
                }
            )
    finally:
        audio.terminate()
    return devices


def parse_arecord_devices(output: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    pattern = re.compile(
        r"card\s+(?P<card>\d+):\s+(?P<card_id>[^\[]+)\[(?P<card_name>[^\]]+)\],\s+"
        r"device\s+(?P<device>\d+):\s+(?P<device_id>[^\[]+)\[(?P<device_name>[^\]]+)\]"
    )
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        card = int(match.group("card"))
        device = int(match.group("device"))
        card_name = match.group("card_name").strip()
        device_name = match.group("device_name").strip()
        devices.append(
            {
                "backend": "arecord",
                "index": f"hw:{card},{device}",
                "device_id": f"plughw:{card},{device}",
                "hardware_id": f"hw:{card},{device}",
                "card": card,
                "device": device,
                "name": f"{card_name} {device_name}".strip(),
                "max_input_channels": 1,
                "default_sample_rate": 16000.0,
            }
        )
    return devices


def _arecord_input_devices() -> list[dict[str, Any]]:
    if shutil.which("arecord") is None:
        return []
    result = subprocess.run(["arecord", "-l"], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"arecord -l failed: {result.stderr.strip() or result.stdout.strip()}")
    return parse_arecord_devices(result.stdout)


def list_input_devices() -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    try:
        devices.extend(_pyaudio_input_devices())
    except RuntimeError:
        pass
    try:
        devices.extend(_arecord_input_devices())
    except RuntimeError:
        if not devices:
            raise
    if devices:
        return devices
    raise RuntimeError(
        "No audio input devices found through PyAudio or arecord. "
        "Check the USB microphone connection, or use --mock-text for fallback."
    )


def choose_input_device(devices: list[dict[str, Any]], requested: str | None = None) -> dict[str, Any]:
    if not devices:
        raise RuntimeError("No audio input devices found. Check that the USB microphone is connected.")

    if requested:
        requested_text = str(requested).strip()
        lowered = requested_text.lower()
        for device in devices:
            if lowered in {
                str(device.get("index")).lower(),
                str(device.get("device_id")).lower(),
                str(device.get("hardware_id")).lower(),
            }:
                return device

        if requested_text.isdigit():
            requested_index = int(requested_text)
            for device in devices:
                if isinstance(device.get("index"), int) and int(device["index"]) == requested_index:
                    return device
                if int(device.get("card") or -1) == requested_index:
                    return device
            raise RuntimeError(f"Audio input device index not found: {requested_index}")

        matches = [
            device
            for device in devices
            if lowered in str(device["name"]).lower()
        ]
        if matches:
            return matches[0]
        raise RuntimeError(f"Audio input device name not found: {requested_text}")

    preferred_markers = ("usb", "microphone", "mic", "麦克风")
    preferred_devices: list[dict[str, Any]] = []
    for device in devices:
        name = str(device["name"]).lower()
        if any(marker in name for marker in preferred_markers):
            preferred_devices.append(device)
    for device in preferred_devices:
        if device.get("backend") == "arecord":
            return device
    if preferred_devices:
        return preferred_devices[0]
    return devices[0]


def print_devices(devices: list[dict[str, Any]]) -> None:
    if not devices:
        print("No audio input devices found.")
        return
    for device in devices:
        print(
            f"{device['index']}: {device['name']} "
            f"(backend={device.get('backend')}, inputs={device['max_input_channels']}, "
            f"default_rate={device['default_sample_rate']:.0f})"
        )


def _dbfs(amplitude: float) -> float:
    if amplitude <= 0:
        return float("-inf")
    return round(20.0 * math.log10(amplitude / 32768.0), 3)


def wav_format(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    with wave.open(str(target), "rb") as wav:
        return {
            "path": str(target),
            "sample_rate": wav.getframerate(),
            "channels": wav.getnchannels(),
            "sample_width": wav.getsampwidth(),
            "frame_count": wav.getnframes(),
            "duration_ms": int(round(wav.getnframes() * 1000 / wav.getframerate()))
            if wav.getframerate()
            else 0,
        }


def wav_level_report(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    with wave.open(str(target), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frame_count = wav.getnframes()
        pcm = wav.readframes(frame_count)

    report: dict[str, Any] = {
        "path": str(target),
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "frame_count": frame_count,
        "duration_ms": int(round(frame_count * 1000 / sample_rate)) if sample_rate else 0,
        "target_max_volume_dbfs": [TARGET_MAX_DBFS_MIN, TARGET_MAX_DBFS_MAX],
    }
    if sample_width != ASR_SAMPLE_WIDTH:
        report.update(
            {
                "max_volume_dbfs": None,
                "rms_dbfs": None,
                "clipping_percent": None,
                "gain_status": "unsupported_sample_width",
            }
        )
        return report

    usable = len(pcm) - (len(pcm) % 2)
    if usable <= 0:
        report.update(
            {
                "max_volume_dbfs": None,
                "rms_dbfs": None,
                "clipping_percent": 0.0,
                "gain_status": "empty_audio",
            }
        )
        return report

    samples = struct.unpack("<" + "h" * (usable // 2), pcm[:usable])
    max_abs = max(abs(sample) for sample in samples)
    mean_square = sum((sample / 32768.0) ** 2 for sample in samples) / len(samples)
    clipping_count = sum(1 for sample in samples if abs(sample) >= 32767)
    clipping_percent = round(clipping_count * 100.0 / len(samples), 4)
    max_volume_dbfs = _dbfs(float(max_abs))
    rms_dbfs = _dbfs(math.sqrt(mean_square) * 32768.0)

    if clipping_count > 0 or max_volume_dbfs >= -1.0:
        gain_status = "clipping_or_too_hot"
    elif TARGET_MAX_DBFS_MIN <= max_volume_dbfs <= TARGET_MAX_DBFS_MAX:
        gain_status = "ok"
    elif max_volume_dbfs < -25.0:
        gain_status = "too_low"
    elif max_volume_dbfs > TARGET_MAX_DBFS_MAX:
        gain_status = "too_hot"
    else:
        gain_status = "usable_but_low"

    report.update(
        {
            "max_abs": max_abs,
            "max_volume_dbfs": max_volume_dbfs,
            "rms_dbfs": rms_dbfs,
            "clipping_samples": clipping_count,
            "clipping_percent": clipping_percent,
            "gain_status": gain_status,
        }
    )
    return report


def ensure_asr_wav_format(
    audio_path: str | Path,
    *,
    sample_rate: int = ASR_SAMPLE_RATE,
    channels: int = ASR_CHANNELS,
) -> tuple[Path, dict[str, Any]]:
    source = Path(audio_path)
    source_format = wav_format(source)
    format_ok = (
        source_format["sample_rate"] == sample_rate
        and source_format["channels"] == channels
        and source_format["sample_width"] == ASR_SAMPLE_WIDTH
    )
    if format_ok:
        return source, {
            "converted": False,
            "source": source_format,
            "asr": source_format,
            "target": {
                "sample_rate": sample_rate,
                "channels": channels,
                "sample_width": ASR_SAMPLE_WIDTH,
                "format": "pcm_s16le",
            },
        }

    target = source.with_name(f"{source.stem}.asr.wav")
    try:
        _convert_wav_to_asr_format_python(source, target, sample_rate=sample_rate, channels=channels)
        return target, {
            "converted": True,
            "converter": "python_audioop",
            "source": source_format,
            "asr": wav_format(target),
            "target": {
                "sample_rate": sample_rate,
                "channels": channels,
                "sample_width": ASR_SAMPLE_WIDTH,
                "format": "pcm_s16le",
            },
        }
    except Exception as python_exc:
        python_error = str(python_exc)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "Failed to convert microphone WAV to 16 kHz mono pcm_s16le for ASR "
            f"with Python audioop ({python_error}), and ffmpeg is not installed."
        )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-acodec",
        "pcm_s16le",
        str(target),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio format conversion failed: {result.stderr.strip()}")
    return target, {
        "converted": True,
        "converter": "ffmpeg",
        "source": source_format,
        "asr": wav_format(target),
        "target": {
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_width": ASR_SAMPLE_WIDTH,
            "format": "pcm_s16le",
        },
        "command": " ".join(command),
    }


def _convert_wav_to_asr_format_python(
    source: Path,
    target: Path,
    *,
    sample_rate: int,
    channels: int,
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import audioop

    with wave.open(str(source), "rb") as wav:
        source_channels = wav.getnchannels()
        source_sample_width = wav.getsampwidth()
        source_sample_rate = wav.getframerate()
        pcm = wav.readframes(wav.getnframes())

    if source_sample_width != ASR_SAMPLE_WIDTH:
        pcm = audioop.lin2lin(pcm, source_sample_width, ASR_SAMPLE_WIDTH)
        source_sample_width = ASR_SAMPLE_WIDTH
    if source_channels > 1:
        pcm = audioop.tomono(pcm, source_sample_width, 0.5, 0.5)
        source_channels = 1
    if source_channels != channels:
        raise RuntimeError(f"Unsupported channel conversion: {source_channels} -> {channels}")
    if source_sample_rate != sample_rate:
        pcm, _ = audioop.ratecv(
            pcm,
            source_sample_width,
            channels,
            source_sample_rate,
            sample_rate,
            None,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(ASR_SAMPLE_WIDTH)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)


def record_wav(
    *,
    device: dict[str, Any],
    output_path: str | Path,
    duration_seconds: float,
    sample_rate: int = 16000,
    channels: int = 1,
    frames_per_buffer: int = 1024,
) -> Path:
    if device.get("backend") == "arecord":
        return record_wav_arecord(
            device_id=str(device["device_id"]),
            output_path=output_path,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            channels=channels,
        )

    pyaudio = import_pyaudio()
    audio = pyaudio.PyAudio()
    stream = None
    frames: list[bytes] = []
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            input=True,
            input_device_index=int(device["index"]),
            frames_per_buffer=frames_per_buffer,
        )
        chunks = max(1, int(sample_rate / frames_per_buffer * duration_seconds))
        for _ in range(chunks):
            frames.append(stream.read(frames_per_buffer, exception_on_overflow=False))
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        audio.terminate()

    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))
    return target


def record_wav_arecord(
    *,
    device_id: str,
    output_path: str | Path,
    duration_seconds: float,
    sample_rate: int,
    channels: int,
) -> Path:
    if shutil.which("arecord") is None:
        raise RuntimeError("arecord is not installed; cannot record without PyAudio.")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(1, int(round(duration_seconds)))
    command = [
        "arecord",
        "-D",
        device_id,
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        str(channels),
        "-d",
        str(seconds),
        str(target),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"arecord failed: {result.stderr.strip() or result.stdout.strip()}")
    return target


async def transcribe_audio_file(args: argparse.Namespace, audio_path: Path) -> dict[str, Any]:
    trim_path = audio_path.with_name(f"{audio_path.stem}.trim.wav") if args.trim_speech else None
    return await run_asr_once(
        source="audio_file",
        audio_path=str(audio_path),
        vad_backend=args.vad_backend,
        vad_threshold=args.vad_threshold,
        asr_backend=args.asr_backend,
        asr_model_path=args.asr_model_path,
        device=args.asr_device,
        no_agent=True,
        trim_speech=args.trim_speech,
        speech_trim_path=str(trim_path) if trim_path else None,
        speech_trim_threshold=args.speech_trim_threshold,
        speech_trim_padding_ms=args.speech_trim_padding_ms,
        speech_trim_min_speech_ms=args.speech_trim_min_speech_ms,
        speech_trim_start_padding_ms=args.speech_trim_start_padding_ms,
        speech_trim_end_padding_ms=args.speech_trim_end_padding_ms,
    )


def build_openclaw_context(
    *,
    transcript: str,
    source: str,
    audio_device: str | None = None,
    audio_path: str | None = None,
    asr_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": OPENCLAW_CONTEXT_SCHEMA_VERSION,
        "event_type": "asr.transcript",
        "demo_intent": DEMO_INTENT,
        "transcript": transcript,
        "source": CONTEXT_SOURCE,
        "transcript_source": source,
        "timestamp": now_iso(),
        "robot_state": {
            "online": "unknown",
            "busy": "unknown",
            "battery": "unknown",
            "dock": "unknown",
        },
        "vision_context": {
            "available": False,
            "summary": "",
        },
        "last_action": None,
        "allowed_actions": allowed_actions_spec(),
        "openclaw_tool_contract": openclaw_tool_contract(),
        "audio": {
            "device": audio_device,
            "path": audio_path,
        },
        "asr_output": asr_output or {},
    }


def _allowed_values(allowed_actions: dict[str, Any], action_name: str, field: str) -> list[str]:
    spec = allowed_actions.get(action_name)
    if not isinstance(spec, dict):
        return []
    values = spec.get(field)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def validate_action_plan(plan: dict[str, Any]) -> dict[str, Any]:
    allowed_actions = plan.get("allowed_actions")
    if not isinstance(allowed_actions, dict):
        allowed_actions = allowed_actions_spec()

    errors: list[str] = []
    actions = plan.get("actions")
    if not isinstance(actions, list):
        errors.append("actions must be a list")
        actions = []

    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"actions[{index}] must be an object")
            continue
        name = str(action.get("name") or "")
        arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
        if name not in allowed_actions:
            errors.append(f"actions[{index}].name not allowed: {name}")
            continue

        if name == "display.expression":
            expression = str(arguments.get("expression") or "")
            if expression not in _allowed_values(allowed_actions, name, "expression"):
                errors.append(f"actions[{index}].arguments.expression not allowed: {expression}")
        elif name == "motion.execute":
            motion = str(arguments.get("action") or "")
            if motion not in _allowed_values(allowed_actions, name, "action"):
                errors.append(f"actions[{index}].arguments.action not allowed: {motion}")
        elif name == "audio.play_local":
            audio_id = str(arguments.get("audio_id") or arguments.get("sound") or "")
            if audio_id not in _allowed_values(allowed_actions, name, "audio_id"):
                errors.append(f"actions[{index}].arguments.audio_id not allowed: {audio_id}")
        elif name == "audio.play_tts":
            spec = allowed_actions.get(name)
            if not isinstance(spec, dict) or spec.get("mode") != "mock_tone_only":
                errors.append(f"actions[{index}].audio.play_tts must be mock_tone_only")

    return {
        "ok": not errors,
        "errors": errors,
    }


def normalize_expression_for_gateway(expression: str) -> str:
    return expression


def normalize_motion_for_gateway(arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    requested = str(arguments.get("action") or "move_out_of_dock")
    params = dict(arguments.get("params") or {}) if isinstance(arguments.get("params"), dict) else {}

    if requested == "left":
        try:
            angle_deg = float(params.get("angle_deg", DEFAULT_TURN_ANGLE_DEG))
        except (TypeError, ValueError):
            angle_deg = DEFAULT_TURN_ANGLE_DEG
        params["angle_deg"] = -abs(angle_deg)
        return "turn", params
    if requested == "right":
        try:
            angle_deg = float(params.get("angle_deg", DEFAULT_TURN_ANGLE_DEG))
        except (TypeError, ValueError):
            angle_deg = DEFAULT_TURN_ANGLE_DEG
        params["angle_deg"] = abs(angle_deg)
        return "turn", params

    return MOTION_GATEWAY_ALIASES.get(requested, requested), params


def post_motion_delay_seconds(arguments: dict[str, Any]) -> float:
    try:
        timeout_ms = int(arguments.get("timeout_ms", 1200))
    except (TypeError, ValueError):
        timeout_ms = 1200
    return max(0.2, min(3.0, timeout_ms / 1000.0 + 0.15))


def detect_expression_request(text: str) -> tuple[str, str] | None:
    if not any(keyword in text for keyword in EXPRESSION_REQUEST_KEYWORDS):
        return None
    for expression, reason, keywords in EXPRESSION_KEYWORD_RULES:
        if any(keyword in text for keyword in keywords):
            return expression, reason
    return None


def detect_unsupported_expression_request(text: str) -> str | None:
    if not any(keyword in text for keyword in EXPRESSION_REQUEST_KEYWORDS):
        return None
    for keyword in UNSUPPORTED_EXPRESSION_KEYWORDS:
        if keyword in text:
            return keyword
    return None


def build_rule_action_plan(transcript: str) -> dict[str, Any]:
    text = transcript.strip()
    fatigue_keywords = ("累", "困", "疲劳", "疲勞", "低落", "烦", "煩", "陪陪")
    approach_keywords = ("过来", "過來", "来一下", "過來一下", "小安")
    unsupported_expression = detect_unsupported_expression_request(text)
    if unsupported_expression:
        plan = {
            "schema_version": ACTION_PLAN_SCHEMA_VERSION,
            "demo_intent": DEMO_INTENT,
            "timestamp": now_iso(),
            "route": "demo1_rule_unsupported_expression",
            "reason": f"unsupported_expression_keyword:{unsupported_expression}",
            "handled": False,
            "allowed_actions": allowed_actions_spec(),
            "actions": [],
        }
        plan["validation"] = validate_action_plan(plan)
        return plan

    expression_request = detect_expression_request(text)
    if expression_request:
        expression, reason = expression_request
        plan = {
            "schema_version": ACTION_PLAN_SCHEMA_VERSION,
            "demo_intent": DEMO_INTENT,
            "timestamp": now_iso(),
            "route": "demo1_rule_expression",
            "reason": reason,
            "handled": True,
            "allowed_actions": allowed_actions_spec(),
            "actions": [
                {
                    "name": "display.expression",
                    "arguments": {
                        "expression": expression,
                        "duration_ms": 3000,
                    },
                },
            ],
        }
        plan["validation"] = validate_action_plan(plan)
        return plan

    should_care = any(keyword in text for keyword in fatigue_keywords)
    should_approach = any(keyword in text for keyword in approach_keywords)

    if not should_care and not should_approach:
        plan = {
            "schema_version": ACTION_PLAN_SCHEMA_VERSION,
            "demo_intent": DEMO_INTENT,
            "timestamp": now_iso(),
            "route": "demo1_rule_noop",
            "reason": "no_demo_keyword",
            "handled": False,
            "allowed_actions": allowed_actions_spec(),
            "actions": [],
        }
        plan["validation"] = validate_action_plan(plan)
        return plan

    actions = [
        {
            "name": "display.expression",
            "arguments": {
                "expression": "caring" if should_care else "happy",
                "duration_ms": 3000,
            },
        },
        {
            "name": "motion.execute",
            "arguments": {
                "action": "move_out_of_dock",
                "params": {"speed": 1.0, "distance_cm": 10.0},
                "timeout_ms": 1200,
            },
        },
    ]
    if should_care:
        actions.append(
            {
                "name": "motion.execute",
                "arguments": {
                    "action": "left",
                    "params": {"speed": 1.0, "angle_deg": -20},
                    "timeout_ms": 700,
                },
            }
        )
        actions.append(
            {
                "name": "audio.play_local",
                "arguments": {
                    "audio_id": "care_01",
                    "sound": "care_01",
                    "volume": 0.7,
                },
            }
        )

    plan = {
        "schema_version": ACTION_PLAN_SCHEMA_VERSION,
        "demo_intent": DEMO_INTENT,
        "timestamp": now_iso(),
        "route": "demo1_rule_care" if should_care else "demo1_rule_approach",
        "reason": "fatigue_keyword" if should_care else "approach_keyword",
        "handled": True,
        "allowed_actions": allowed_actions_spec(),
        "actions": actions,
    }
    plan["validation"] = validate_action_plan(plan)
    return plan


def build_openclaw_asr_event(
    *,
    transcript: str,
    context: dict[str, Any],
    session_id: str,
) -> OpenClawEvent:
    return OpenClawEvent(
        type="asr.transcript",
        text=transcript,
        source=CONTEXT_SOURCE,
        session_id=session_id,
        context=context,
    )


def validate_openclaw_decision(decision: OpenClawDecision) -> dict[str, Any]:
    contract = openclaw_tool_contract()
    allowed_tools = set(contract["allowed_tools"])
    allowed_expressions = set(contract["allowed_expressions"])
    errors: list[str] = []

    if not decision.handled:
        errors.append("decision.handled must be true for Demo 1 main path")
    if not decision.tool_calls:
        errors.append("decision.tool_calls must be non-empty for Demo 1 main path")

    for index, tool_call in enumerate(decision.tool_calls):
        if tool_call.name not in allowed_tools:
            errors.append(f"tool_calls[{index}].name not allowed: {tool_call.name}")
            continue
        if tool_call.name == "xiaoan.robot.expression":
            expression = str(tool_call.arguments.get("expression") or "")
            if expression not in allowed_expressions:
                errors.append(
                    f"tool_calls[{index}].arguments.expression not allowed: {expression}"
                )
        elif tool_call.name == "xiaoan.robot.say":
            text = str(tool_call.arguments.get("text") or "").strip()
            if not text:
                errors.append(f"tool_calls[{index}].arguments.text is required")

    return {
        "ok": not errors,
        "errors": errors,
        "allowed_tools": sorted(allowed_tools),
        "allowed_expressions": sorted(allowed_expressions),
    }


def _executed_tool_call_actions(execution: dict[str, Any]) -> list[dict[str, Any]]:
    actions = execution.get("executed_actions")
    if not isinstance(actions, list):
        return []
    return [
        action
        for action in actions
        if isinstance(action, dict) and action.get("source") == "tool_call"
    ]


def openclaw_execution_ok(execution: dict[str, Any]) -> bool:
    skipped = execution.get("skipped_actions")
    return (
        not bool(execution.get("openclaw_error"))
        and bool(_executed_tool_call_actions(execution))
        and not bool(skipped)
    )


def validate_main_openclaw_artifacts(
    *,
    transcript: str,
    context: dict[str, Any],
    action_plan: dict[str, Any],
    openclaw_result: dict[str, Any],
    expected_gateway_url: str = DEFAULT_OPENCLAW_GATEWAY_URL,
    expected_agent: str = DEFAULT_OPENCLAW_AGENT,
    require_robot_execution: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []

    if context.get("schema_version") != OPENCLAW_CONTEXT_SCHEMA_VERSION:
        errors.append("context.schema_version must be demo1.openclaw_context.v1")
    if context.get("event_type") != "asr.transcript":
        errors.append("context.event_type must be asr.transcript")
    if context.get("source") != CONTEXT_SOURCE:
        errors.append("context.source must be base_station_mic")
    if context.get("transcript") != transcript:
        errors.append("context.transcript must equal transcript")

    route = action_plan.get("route")
    if route != "openclaw_gateway":
        errors.append(f"action_plan.route must be openclaw_gateway, got {route}")
    if action_plan.get("reason") != "openclaw_decision_owner":
        errors.append("action_plan.reason must be openclaw_decision_owner")
    if action_plan.get("actions") != []:
        errors.append("action_plan.actions must be empty on the OpenClaw-owned main path")
    if isinstance(route, str) and (route.startswith("demo1_rule_") or route == "legacy_rule_agent"):
        errors.append("local rule route cannot be Demo 1 main success evidence")

    if openclaw_result.get("attempted") is not True:
        errors.append("openclaw_result.attempted must be true")
    if openclaw_result.get("ok") is not True:
        errors.append("openclaw_result.ok must be true")
    if openclaw_result.get("gateway_url") != expected_gateway_url:
        errors.append("openclaw_result.gateway_url mismatch")
    if openclaw_result.get("agent") != expected_agent:
        errors.append("openclaw_result.agent mismatch")

    event = openclaw_result.get("event")
    if not isinstance(event, dict):
        errors.append("openclaw_result.event must be an object")
        event = {}
    if event.get("text") != transcript:
        errors.append("openclaw_result.event.text must equal transcript")
    if event.get("source") != CONTEXT_SOURCE:
        errors.append("openclaw_result.event.source must be base_station_mic")

    decision = openclaw_result.get("decision")
    if not isinstance(decision, dict):
        errors.append("openclaw_result.decision must be an object")
        decision = {}
    if decision.get("handled") is not True:
        errors.append("openclaw_result.decision.handled must be true")
    tool_calls = decision.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        errors.append("openclaw_result.decision.tool_calls must be non-empty")

    decision_validation = openclaw_result.get("decision_validation")
    if not isinstance(decision_validation, dict):
        errors.append("openclaw_result.decision_validation must be an object")
        decision_validation = {}
    if decision_validation.get("ok") is not True:
        errors.append("openclaw_result.decision_validation.ok must be true")

    execution = openclaw_result.get("execution")
    if not isinstance(execution, dict):
        errors.append("openclaw_result.execution must be an object")
        execution = {}
    executed_actions = execution.get("executed_actions")
    decision_only = execution.get("mode") == "openclaw_decision_only"
    if require_robot_execution:
        if not isinstance(executed_actions, list) or not executed_actions:
            errors.append("openclaw_result.execution.executed_actions must be non-empty")
        if not _executed_tool_call_actions(execution):
            errors.append("execution must include at least one executed tool_call action")
        if execution.get("skipped_actions"):
            errors.append("execution.skipped_actions must be empty for main success")
    elif not decision_only and not _executed_tool_call_actions(execution):
        errors.append("execution must be openclaw_decision_only or include an executed tool_call action")

    return {"ok": not errors, "errors": errors}


async def send_action_plan_to_agent(plan: dict[str, Any], gateway_url: str) -> dict[str, Any]:
    validation = validate_action_plan(plan)
    if not validation["ok"]:
        return {
            "attempted": False,
            "ok": False,
            "gateway_url": gateway_url,
            "validation": validation,
            "results": [],
        }

    gateway = RobotGateway(url=gateway_url)
    results: list[dict[str, Any]] = []
    for index, action in enumerate(plan.get("actions") or []):
        name = str(action.get("name") or "")
        arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
        result: dict[str, Any] = {
            "index": index,
            "name": name,
            "arguments": arguments,
            "ok": False,
        }
        try:
            if name == "display.expression":
                result["ack"] = await gateway.send_expression(
                    normalize_expression_for_gateway(str(arguments.get("expression") or "caring")),
                    duration_ms=int(arguments.get("duration_ms") or 3000),
                    loop=bool(arguments.get("loop", False)),
                )
            elif name == "motion.execute":
                gateway_action, gateway_params = normalize_motion_for_gateway(arguments)
                result["gateway_action"] = gateway_action
                result["gateway_params"] = gateway_params
                result["ack"] = await gateway.send_motion(
                    gateway_action,
                    params=gateway_params,
                    timeout_ms=int(arguments.get("timeout_ms") or 1200),
                )
                result["post_send_delay_sec"] = post_motion_delay_seconds(arguments)
                await asyncio.sleep(float(result["post_send_delay_sec"]))
            elif name == "audio.play_local":
                result["ack"] = await gateway.send_local_audio(
                    str(arguments.get("audio_id") or arguments.get("sound") or "care_01"),
                )
            elif name == "audio.play_tts":
                result["ack"] = await gateway.send_tts(str(arguments.get("text") or ""))
            else:
                result["error"] = f"Unsupported demo action: {name}"
        except Exception as exc:
            result["error"] = str(exc)
        else:
            result["ok"] = True
        results.append(result)

    return {
        "attempted": bool(plan.get("actions")),
        "ok": bool(results) and all(item.get("ok") for item in results),
        "gateway_url": gateway_url,
        "validation": validation,
        "results": results,
    }


async def send_transcript_to_openclaw(
    args: argparse.Namespace,
    *,
    transcript: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    event = build_openclaw_asr_event(
        transcript=transcript,
        context=context,
        session_id=args.openclaw_session_id,
    )
    adapter = GatewayOpenClawAdapter(
        gateway_url=args.openclaw_gateway_url,
        agent=args.openclaw_agent,
        timeout_sec=float(args.openclaw_timeout_sec),
        gateway_token=args.openclaw_gateway_token,
        tools=demo1_openclaw_tool_manifest(),
    )
    decision = await asyncio.to_thread(adapter.handle_event, event)
    decision_validation = validate_openclaw_decision(decision)
    if not decision_validation["ok"]:
        result = {
            "attempted": True,
            "ok": False,
            "gateway_url": args.openclaw_gateway_url,
            "agent": args.openclaw_agent,
            "session_id": args.openclaw_session_id,
            "event": event.to_dict(),
            "decision": decision.to_dict(),
            "decision_validation": decision_validation,
            "execution": {
                "handled": False,
                "skipped_actions": [],
                "executed_actions": [],
                "openclaw_error": "OpenClaw decision failed Demo 1 validation",
            },
        }
        write_json_artifact(args.openclaw_result_path, result)
        return result

    if getattr(args, "openclaw_decision_only", False):
        execution = {
            "handled": False,
            "mode": "openclaw_decision_only",
            "robot_execution_skipped": True,
            "skipped_actions": [
                {
                    "name": tool_call.name,
                    "source": "tool_call",
                    "reason": "openclaw_decision_only",
                    "arguments": tool_call.arguments,
                }
                for tool_call in decision.tool_calls
            ],
            "executed_actions": [],
            "openclaw_error": None,
        }
        result = {
            "attempted": True,
            "ok": True,
            "gateway_url": args.openclaw_gateway_url,
            "agent": args.openclaw_agent,
            "session_id": args.openclaw_session_id,
            "event": event.to_dict(),
            "decision": decision.to_dict(),
            "decision_validation": decision_validation,
            "execution": execution,
        }
        write_json_artifact(args.openclaw_result_path, result)
        return result

    gateway = RobotGateway(url=args.gateway_url)
    executor = ActionExecutor(RobotMotionSkill(gateway=gateway), memory_store=None)
    execution = await executor.execute(decision, source_event_type="asr.transcript")
    result = {
        "attempted": True,
        "ok": bool(decision.handled) and openclaw_execution_ok(execution),
        "gateway_url": args.openclaw_gateway_url,
        "agent": args.openclaw_agent,
        "session_id": args.openclaw_session_id,
        "event": event.to_dict(),
        "decision": decision.to_dict(),
        "decision_validation": decision_validation,
        "execution": execution,
    }
    write_json_artifact(args.openclaw_result_path, result)
    return result


def resolve_route_mode(args: argparse.Namespace) -> str:
    if getattr(args, "route_openclaw", False):
        return "openclaw"
    if getattr(args, "route_agent", False):
        return "legacy_rule_agent"
    return "context_only"


async def route_transcript_if_requested(
    args: argparse.Namespace,
    *,
    transcript: str,
    transcript_source: str,
    audio_device: str | None = None,
    audio_path: str | None = None,
    asr_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route_mode = resolve_route_mode(args)
    context = build_openclaw_context(
        transcript=transcript,
        source=transcript_source,
        audio_device=audio_device,
        audio_path=audio_path,
        asr_output=asr_output,
    )
    write_json_artifact(args.context_path, context)

    route_result: dict[str, Any] = {
        "enabled": route_mode != "context_only",
        "route_mode": route_mode,
        "context_path": str(Path(args.context_path)),
        "plan_path": str(Path(args.plan_path)),
        "openclaw_result_path": str(Path(args.openclaw_result_path)),
        "context": context,
        "action_plan": None,
        "openclaw_send": None,
        "agent_send": None,
    }

    if route_mode == "openclaw":
        gateway_plan = build_no_decision_plan(
            route="openclaw_gateway",
            reason="openclaw_decision_owner",
        )
        gateway_plan["note"] = "No local rule action plan was executed; see openclaw_result_path."
        write_json_artifact(args.plan_path, gateway_plan)
        route_result["action_plan"] = gateway_plan
        route_result["openclaw_send"] = await send_transcript_to_openclaw(
            args,
            transcript=transcript,
            context=context,
        )
        return route_result

    if route_mode == "context_only":
        plan = build_no_decision_plan(
            route="context_only",
            reason="no_decision_route_enabled",
        )
        write_json_artifact(args.plan_path, plan)
        route_result["action_plan"] = plan
        return route_result

    plan = build_rule_action_plan(transcript)
    write_json_artifact(args.plan_path, plan)
    route_result["action_plan"] = plan

    if route_mode == "legacy_rule_agent":
        route_result["agent_send"] = await send_action_plan_to_agent(
            plan,
            gateway_url=args.gateway_url,
        )
    return route_result


def make_screen_html(state: dict[str, Any]) -> bytes:
    status = html.escape(str(state.get("status") or "idle"))
    transcript = html.escape(str(state.get("transcript") or "等待识别..."))
    source = html.escape(str(state.get("source") or "--"))
    timestamp = html.escape(str(state.get("timestamp") or "--"))
    device = html.escape(str(state.get("audio_device") or "--"))
    error = html.escape(str(state.get("error") or ""))
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{DEMO_TITLE}</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: #101416;
      color: #f5f7f8;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #101416;
    }}
    main {{
      width: min(980px, calc(100vw - 48px));
    }}
    h1 {{
      margin: 0 0 28px;
      font-size: 42px;
      font-weight: 800;
      letter-spacing: 0;
    }}
    .status {{
      display: inline-flex;
      padding: 8px 14px;
      border: 1px solid #4d6b73;
      border-radius: 6px;
      color: #9ee7d8;
      font-size: 22px;
      font-weight: 700;
    }}
    .transcript {{
      margin: 28px 0;
      padding: 28px 0;
      border-top: 1px solid #2d3a3d;
      border-bottom: 1px solid #2d3a3d;
      font-size: 46px;
      line-height: 1.35;
      font-weight: 800;
      word-break: break-word;
    }}
    dl {{
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 12px 20px;
      font-size: 20px;
      color: #cbd7da;
    }}
    dt {{
      color: #88a1a8;
    }}
    dd {{
      margin: 0;
      word-break: break-word;
    }}
    .error {{
      color: #ffb4a8;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{DEMO_TITLE}</h1>
    <div class="status">状态：<span id="status">{status}</span></div>
    <section class="transcript">最近识别内容：<span id="transcript">{transcript}</span></section>
    <dl>
      <dt>来源</dt><dd id="source">{source}</dd>
      <dt>时间</dt><dd id="timestamp">{timestamp}</dd>
      <dt>音频设备</dt><dd id="device">{device}</dd>
      <dt>错误</dt><dd id="error" class="error">{error}</dd>
    </dl>
  </main>
  <script>
    async function refresh() {{
      try {{
        const response = await fetch('/api/demo1/transcript', {{cache: 'no-store'}});
        const state = await response.json();
        document.getElementById('status').textContent = state.status || 'idle';
        document.getElementById('transcript').textContent = state.transcript || '等待识别...';
        document.getElementById('source').textContent = state.source || '--';
        document.getElementById('timestamp').textContent = state.timestamp || '--';
        document.getElementById('device').textContent = state.audio_device || '--';
        document.getElementById('error').textContent = state.error || '';
      }} catch (err) {{
        document.getElementById('error').textContent = String(err);
      }}
    }}
    setInterval(refresh, 1000);
    refresh();
  </script>
</body>
</html>
"""
    return body.encode("utf-8")


def make_handler(state_path: Path):
    class Demo1ScreenHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return None

        def do_GET(self) -> None:
            if self.path in {"/", "/demo1"}:
                self._write(200, "text/html; charset=utf-8", make_screen_html(load_state(state_path)))
                return
            if self.path == "/api/demo1/transcript":
                payload = json.dumps(load_state(state_path), ensure_ascii=False, indent=2).encode("utf-8")
                self._write(200, "application/json; charset=utf-8", payload)
                return
            self._write(404, "text/plain; charset=utf-8", b"not found")

        def _write(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Demo1ScreenHandler


def start_screen_server(host: str, port: int, state_path: Path) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, int(port)), make_handler(state_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def audio_output_path(audio_dir: Path) -> Path:
    return audio_dir / f"demo1_usb_mic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"


def recording_sample_rate(device: dict[str, Any], requested_sample_rate: int) -> int:
    if device.get("backend") != "pyaudio":
        return requested_sample_rate
    default_rate = int(float(device.get("default_sample_rate") or 0))
    return default_rate if default_rate > 0 else requested_sample_rate
    return requested_sample_rate


async def run_demo(args: argparse.Namespace) -> int:
    state_path = Path(args.state_path)
    text_path = Path(args.text_path)
    context_path = Path(args.context_path)
    plan_path = Path(args.plan_path)
    log_path = Path(args.log_path)
    audio_dir = Path(args.audio_dir)
    route_mode = resolve_route_mode(args)
    server = None

    if args.list_devices:
        print_devices(list_input_devices())
        return 0

    update_state(
        state_path,
        log_path,
        status="idle",
        details={
            "screen_url": args.screen_url,
            "text_path": str(text_path),
            "context_path": str(context_path),
            "plan_path": str(plan_path),
            "openclaw_result_path": str(args.openclaw_result_path),
            "route_mode": route_mode,
            "route_openclaw": args.route_openclaw,
            "route_agent": args.route_agent,
            "openclaw_gateway_url": args.openclaw_gateway_url,
            "openclaw_agent": args.openclaw_agent,
        },
    )
    if not args.no_screen:
        server = start_screen_server(args.host, args.port, state_path)
        print(f"Demo 1 screen: {args.screen_url}")

    try:
        if args.mock_text is not None:
            write_transcript_text(text_path, args.mock_text)
            route_result = await route_transcript_if_requested(
                args,
                transcript=args.mock_text,
                transcript_source="mock",
            )
            state = update_state(
                state_path,
                log_path,
                status="done",
                transcript=args.mock_text,
                source="mock",
                asr_backend="mock",
                details={
                    "mock_reason": "explicit --mock-text fallback",
                    "text_path": str(text_path),
                    "route_mode": route_mode,
                    "route_result": route_result,
                },
            )
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0

        devices = list_input_devices()
        selected = choose_input_device(devices, args.device)
        device_name = str(selected["name"])
        device_index = selected.get("index")
        sample_rate = recording_sample_rate(selected, args.sample_rate)
        wav_path = audio_output_path(audio_dir)

        update_state(
            state_path,
            log_path,
            status="listening",
            source="asr",
            audio_device=device_name,
            audio_device_index=device_index,
            audio_path=str(wav_path),
            asr_backend=args.asr_backend,
            details={
                "duration_seconds": args.duration,
                "sample_rate": sample_rate,
                "requested_sample_rate": args.sample_rate,
                "asr_target_format": {
                    "sample_rate": ASR_SAMPLE_RATE,
                    "channels": ASR_CHANNELS,
                    "format": "pcm_s16le",
                },
                "audio_backend": selected.get("backend"),
                "audio_device_id": selected.get("device_id"),
                "text_path": str(text_path),
                "route_mode": route_mode,
                "route_openclaw": args.route_openclaw,
                "route_agent": args.route_agent,
            },
        )
        print(f"Recording {args.duration:.1f}s from [{device_index}] {device_name}")
        record_wav(
            device=selected,
            output_path=wav_path,
            duration_seconds=args.duration,
            sample_rate=sample_rate,
            channels=1,
        )
        asr_wav_path, format_report = ensure_asr_wav_format(
            wav_path,
            sample_rate=ASR_SAMPLE_RATE,
            channels=ASR_CHANNELS,
        )
        level_report = wav_level_report(asr_wav_path)

        update_state(
            state_path,
            log_path,
            status="transcribing",
            source="asr",
            audio_device=device_name,
            audio_device_index=device_index,
            audio_path=str(asr_wav_path),
            asr_backend=args.asr_backend,
            details={
                "raw_audio_path": str(wav_path),
                "asr_audio_path": str(asr_wav_path),
                "audio_format": format_report,
                "input_level": level_report,
                "vad_starting_config": {
                    "vad_backend": args.vad_backend,
                    "vad_threshold": args.vad_threshold,
                    "min_speech_ms": args.speech_trim_min_speech_ms,
                    "end_silence_ms": args.speech_trim_end_padding_ms,
                    "pre_roll_ms": args.speech_trim_start_padding_ms,
                    "noise_reduction": "off",
                },
            },
        )
        output = await transcribe_audio_file(args, asr_wav_path)
        transcript = str(output.get("text") or "").strip()
        if not transcript:
            raise RuntimeError(f"ASR returned no transcript: {json.dumps(output, ensure_ascii=False)}")

        write_transcript_text(text_path, transcript)
        update_state(
            state_path,
            log_path,
            status="routing" if route_mode != "context_only" else "planning",
            transcript=transcript,
            source="asr" if args.asr_backend == "sensevoice" else "mock",
            audio_device=device_name,
            audio_device_index=device_index,
            audio_path=str(asr_wav_path),
            asr_backend=args.asr_backend,
            details={
                "text_path": str(text_path),
                "context_path": str(context_path),
                "plan_path": str(plan_path),
                "openclaw_result_path": str(args.openclaw_result_path),
                "route_mode": route_mode,
                "route_openclaw": args.route_openclaw,
                "route_agent": args.route_agent,
                "raw_audio_path": str(wav_path),
                "asr_audio_path": str(asr_wav_path),
                "audio_format": format_report,
                "input_level": level_report,
            },
        )
        route_result = await route_transcript_if_requested(
            args,
            transcript=transcript,
            transcript_source="asr" if args.asr_backend == "sensevoice" else "mock",
            audio_device=device_name,
            audio_path=str(asr_wav_path),
            asr_output=output,
        )
        state = update_state(
            state_path,
            log_path,
            status="done",
            transcript=transcript,
            source="asr" if args.asr_backend == "sensevoice" else "mock",
            audio_device=device_name,
            audio_device_index=device_index,
            audio_path=str(asr_wav_path),
            asr_backend=args.asr_backend,
            details={
                "asr_output": output,
                "text_path": str(text_path),
                "route_mode": route_mode,
                "route_result": route_result,
                "raw_audio_path": str(wav_path),
                "asr_audio_path": str(asr_wav_path),
                "audio_format": format_report,
                "input_level": level_report,
            },
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        message = str(exc)
        if "SenseVoice" in message or "funasr" in message or "ASR" in message:
            message = f"ASR backend unavailable: {message}. Use --mock-text to verify the screen path."
        state = update_state(
            state_path,
            log_path,
            status="error",
            source="asr",
            asr_backend=args.asr_backend,
            error=message,
        )
        print(json.dumps(state, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    finally:
        if server is not None and args.once:
            server.shutdown()
            server.server_close()
        elif server is not None:
            print("Press Ctrl+C to stop the Demo 1 screen server.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                server.shutdown()
                server.server_close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DEMO_TITLE)
    parser.add_argument("--list-devices", action="store_true", help="List audio input devices and exit.")
    parser.add_argument("--device", default=None, help="Audio input device index or name substring. Defaults to USB mic.")
    parser.add_argument("--duration", type=float, default=5.0, help="Recording window in seconds.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--asr-backend", choices=["sensevoice", "fake"], default="sensevoice")
    parser.add_argument("--asr-model-path", default="base_station/models/sensevoice-small")
    parser.add_argument("--asr-device", default="cpu")
    parser.add_argument("--vad-backend", choices=["fake", "energy", "silero"], default="energy")
    parser.add_argument("--vad-threshold", type=float, default=0.003)
    parser.add_argument("--trim-speech", action="store_true", default=True)
    parser.add_argument("--no-trim-speech", dest="trim_speech", action="store_false")
    parser.add_argument("--speech-trim-threshold", type=float, default=0.003)
    parser.add_argument("--speech-trim-padding-ms", type=int, default=250)
    parser.add_argument("--speech-trim-min-speech-ms", type=int, default=350)
    parser.add_argument("--speech-trim-start-padding-ms", type=int, default=250)
    parser.add_argument("--speech-trim-end-padding-ms", type=int, default=800)
    parser.add_argument("--mock-text", default=None, help="Fallback transcript. Does not pretend to be real ASR.")
    parser.add_argument(
        "--route-openclaw",
        action="store_true",
        help="Main Demo 1 path: send ASR context to real OpenClaw Gateway before robot execution.",
    )
    parser.add_argument(
        "--openclaw-decision-only",
        action="store_true",
        help=(
            "Test-only mode for --route-openclaw: validate real OpenClaw tool_calls "
            "and skip base_station /agent robot execution."
        ),
    )
    parser.add_argument(
        "--route-agent",
        action="store_true",
        help="Legacy local-rule route. Not the main OpenClaw demo path.",
    )
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/agent", help="Base station /agent URL.")
    parser.add_argument(
        "--openclaw-gateway-url",
        default=DEFAULT_OPENCLAW_GATEWAY_URL,
        help="OpenClaw Gateway WebSocket URL.",
    )
    parser.add_argument(
        "--openclaw-agent",
        default=DEFAULT_OPENCLAW_AGENT,
        help="OpenClaw agent id, usually xiaoan-runtime.",
    )
    parser.add_argument(
        "--openclaw-timeout-sec",
        type=float,
        default=DEFAULT_OPENCLAW_GATEWAY_TIMEOUT_SEC,
        help="OpenClaw Gateway request timeout.",
    )
    parser.add_argument(
        "--openclaw-gateway-token",
        default=None,
        help="Optional OpenClaw Gateway token. If omitted, adapter reads env/config.",
    )
    parser.add_argument("--openclaw-session-id", default="demo1", help="OpenClaw session id.")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--text-path", default=str(DEFAULT_TEXT_PATH), help="Plain transcript text output path.")
    parser.add_argument("--context-path", default=str(DEFAULT_CONTEXT_PATH), help="OpenClaw/context input artifact path.")
    parser.add_argument("--plan-path", default=str(DEFAULT_PLAN_PATH), help="Demo action plan artifact path.")
    parser.add_argument(
        "--openclaw-result-path",
        default=str(DEFAULT_OPENCLAW_RESULT_PATH),
        help="OpenClaw decision/execution result artifact path.",
    )
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--audio-dir", default=str(DEFAULT_AUDIO_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-screen", action="store_true", help="Do not start the local screen HTTP server.")
    parser.add_argument("--once", action="store_true", help="Exit after one recording/mock cycle instead of keeping screen open.")
    args = parser.parse_args(argv)
    if args.route_openclaw and args.route_agent:
        parser.error("--route-openclaw and --route-agent are mutually exclusive")
    if args.openclaw_decision_only and not args.route_openclaw:
        parser.error("--openclaw-decision-only requires --route-openclaw")
    display_host = "localhost" if args.host in {"127.0.0.1", "0.0.0.0"} else args.host
    args.screen_url = f"http://{display_host}:{args.port}"
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run_demo(parse_args(argv)))
    except KeyboardInterrupt:
        raise
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
