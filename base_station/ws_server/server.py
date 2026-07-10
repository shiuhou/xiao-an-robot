"""
server.py
---------
WebSocket server running on the Intel DK-2500 base station.
Handles four channels: /control /audio /video /agent

Run with: python -m base_station.ws_server.server

Author: Team Xiao An
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Optional

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from base_station.perception.audio_diagnostics import pcm_s16le_stats
from base_station.perception.ws_video_source import VideoFrameDecodeError

from .protocol import (
    Expression,
    MessageType,
    MotionAction,
    make_expression,
    make_audio_stream_end,
    make_motion,
    make_play_local,
    make_play_tts,
    make_welcome,
    parse_message,
)
from .tts_stream import (
    TtsPcmStream,
    external_tts_backend_configured,
    synthesize_tts_pcm_stream,
    tts_backend_runtime_settings,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ws_server")

# Active robot sessions: device_id -> session dict
sessions: Dict[str, dict] = {}
recent_robot_events: Deque[dict] = deque(maxlen=200)
video_frame_source = None
video_observer_queues: set[asyncio.Queue[bytes]] = set()
audio_runtime_dir = Path("runtime")
ws_runtime_dir = Path("runtime")
server_started_at = time.time()
audio_latest_pcm_max_bytes = 16000 * 2 * 5  # 5 seconds of 16kHz mono s16le PCM.
MIN_SAFE_SPEED = 0.52
MAX_SAFE_SPEED = 1.0
DEFAULT_SAFE_SPEED = 1.0
MAX_SAFE_DISTANCE_CM = 10.0
DEFAULT_SAFE_DISTANCE_CM = 10.0
MAX_SAFE_TIMEOUT_MS = 2600
DEFAULT_SAFE_TIMEOUT_MS = 1200
BENCH_MAX_SPEED = 1.0
BENCH_MAX_TIMEOUT_MS = 10000
BENCH_MAX_DISTANCE_CM = 100.0
BENCH_MAX_DURATION_MS = 10000
CONTROL_TTS_CHUNK_BYTES = 2048
CONTROL_TTS_START_DELAY_SECONDS = 0.0
CONTROL_TTS_CHUNK_PACE_RATIO = 0.35
CONTROL_TTS_STREAM_ENV = "XIAOAN_CONTROL_TTS_STREAM"
CONTROL_TTS_CHUNK_BYTES_ENV = "XIAOAN_CONTROL_TTS_CHUNK_BYTES"
CONTROL_TTS_START_DELAY_ENV = "XIAOAN_CONTROL_TTS_START_DELAY_SEC"
CONTROL_TTS_CHUNK_PACE_RATIO_ENV = "XIAOAN_CONTROL_TTS_CHUNK_PACE_RATIO"
CONTROL_TTS_REQUIRE_PLAYBACK_DONE_ENV = "XIAOAN_CONTROL_TTS_REQUIRE_PLAYBACK_DONE"
CONTROL_TTS_PLAYBACK_TIMEOUT_ENV = "XIAOAN_CONTROL_TTS_PLAYBACK_TIMEOUT_SEC"
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
FALSE_ENV_VALUES = {"0", "false", "no", "off"}
audio_playback_waiters: set[asyncio.Future] = set()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _empty_ws_state() -> dict[str, Any]:
    return {
        "updated_at": _now_iso(),
        "server_started_at": datetime.fromtimestamp(server_started_at, timezone.utc).isoformat(),
        "online_devices": [],
        "selected_device_id": None,
        "sessions": {},
        "devices": {},
        "last_command_ack": None,
        "last_motion_completed": None,
        "last_audio_playback_done": None,
        "last_error": None,
        "tts_runtime": {},
        "counters": {
            "control_messages": 0,
            "video_frames": 0,
            "audio_chunks": 0,
            "agent_commands": 0,
        },
    }


ws_state: dict[str, Any] = _empty_ws_state()


def _snapshot_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "device_id": session.get("device_id"),
        "session_id": session.get("session_id"),
        "last_hb": session.get("last_hb"),
        "battery": session.get("battery"),
        "ip": session.get("ip"),
        "wifi_rssi": session.get("wifi_rssi"),
        "free_heap": session.get("free_heap"),
        "reset_reason": session.get("reset_reason"),
        "reset_reason_code": session.get("reset_reason_code"),
        "status": session.get("status"),
    }


def _refresh_ws_sessions_state() -> None:
    ws_state["online_devices"] = sorted(sessions.keys())
    ws_state["selected_device_id"] = ws_state["online_devices"][0] if ws_state["online_devices"] else None
    ws_state["sessions"] = {
        device_id: _snapshot_session(session)
        for device_id, session in sessions.items()
    }


def _merge_device_event(device_id: Optional[str], event_key: str, payload: dict[str, Any]) -> None:
    if not device_id:
        return
    devices = ws_state.setdefault("devices", {})
    device_state = devices.setdefault(device_id, {})
    device_state[event_key] = {
        "received_at": _now_iso(),
        "payload": deepcopy(payload),
    }


def write_ws_state_snapshot(runtime_dir: str | Path | None = None) -> bool:
    """Persist the current WebSocket runtime state without leaking sockets."""

    runtime_path = Path(runtime_dir) if runtime_dir is not None else ws_runtime_dir
    ws_state["updated_at"] = _now_iso()
    ws_state["tts_runtime"] = tts_runtime_settings()
    _refresh_ws_sessions_state()
    try:
        _atomic_write_json(runtime_path / "ws_state.json", ws_state)
    except OSError as exc:
        logger.warning("Failed to write ws_state snapshot: %s", exc)
        return False
    return True


def record_ws_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    device_id: Optional[str] = None,
) -> None:
    payload = payload if isinstance(payload, dict) else {}
    counters = ws_state.setdefault("counters", {})
    if event_type in {
        "device.hello",
        "device.heartbeat",
        "device.status",
        "command.ack",
        "motion.completed",
        "audio.playback_done",
        "error.report",
        "video.frame",
        "video.frame_meta",
        "audio.chunk_meta",
    }:
        counters["control_messages"] = int(counters.get("control_messages", 0)) + 1

    if event_type == "device.hello":
        _merge_device_event(device_id, "last_hello", payload)
    elif event_type == "device.heartbeat":
        _merge_device_event(device_id, "last_heartbeat", payload)
    elif event_type == "device.status":
        _merge_device_event(device_id, "last_status", payload)
    elif event_type == "command.ack":
        ws_state["last_command_ack"] = {"received_at": _now_iso(), "payload": deepcopy(payload)}
    elif event_type == "motion.completed":
        ws_state["last_motion_completed"] = {"received_at": _now_iso(), "payload": deepcopy(payload)}
    elif event_type == "audio.playback_done":
        ws_state["last_audio_playback_done"] = {"received_at": _now_iso(), "payload": deepcopy(payload)}
    elif event_type == "error.report":
        ws_state["last_error"] = {"received_at": _now_iso(), "payload": deepcopy(payload)}
    elif event_type in {"video.frame", "video.frame_meta"}:
        counters["video_frames"] = int(counters.get("video_frames", 0)) + 1
    elif event_type == "audio.chunk_meta":
        counters["audio_chunks"] = int(counters.get("audio_chunks", 0)) + 1

    write_ws_state_snapshot()


def control_tts_stream_enabled() -> bool:
    raw = os.getenv(CONTROL_TTS_STREAM_ENV)
    if raw is None or not raw.strip():
        return external_tts_backend_configured()
    return raw.strip().lower() in TRUE_ENV_VALUES


def control_tts_playback_done_required() -> bool:
    raw = os.getenv(CONTROL_TTS_REQUIRE_PLAYBACK_DONE_ENV)
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in FALSE_ENV_VALUES


def control_tts_playback_timeout_seconds(pcm_stream: TtsPcmStream) -> float:
    raw = os.getenv(CONTROL_TTS_PLAYBACK_TIMEOUT_ENV)
    try:
        override = float(raw) if raw is not None and raw.strip() else None
    except (TypeError, ValueError):
        override = None
    if override is not None and override > 0:
        return override
    expected_seconds = max(0.0, pcm_stream.duration_ms / 1000.0)
    return max(8.0, expected_seconds + control_tts_start_delay_seconds() + 6.0)


def _float_env(name: str, default: float, *, min_value: float, max_value: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw is not None and raw.strip() else default
    except (TypeError, ValueError):
        return default
    if value < min_value or value > max_value:
        return default
    return value


def _int_env(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None and raw.strip() else default
    except (TypeError, ValueError):
        return default
    if value < min_value or value > max_value:
        return default
    return value


def control_tts_chunk_bytes() -> int:
    return _int_env(
        CONTROL_TTS_CHUNK_BYTES_ENV,
        CONTROL_TTS_CHUNK_BYTES,
        min_value=320,
        max_value=8192,
    )


def control_tts_start_delay_seconds() -> float:
    return _float_env(
        CONTROL_TTS_START_DELAY_ENV,
        CONTROL_TTS_START_DELAY_SECONDS,
        min_value=0.0,
        max_value=2.0,
    )


def control_tts_chunk_pace_ratio() -> float:
    return _float_env(
        CONTROL_TTS_CHUNK_PACE_RATIO_ENV,
        CONTROL_TTS_CHUNK_PACE_RATIO,
        min_value=0.1,
        max_value=2.0,
    )


def tts_runtime_settings() -> dict[str, object]:
    settings = tts_backend_runtime_settings()
    raw_stream = os.getenv(CONTROL_TTS_STREAM_ENV, "")
    settings.update({
        "control_stream_env": raw_stream,
        "control_stream_enabled": control_tts_stream_enabled(),
        "playback_done_required": control_tts_playback_done_required(),
        "playback_done_timeout_env": os.getenv(CONTROL_TTS_PLAYBACK_TIMEOUT_ENV, ""),
        "transport": "control_raw_pcm_stream",
        "chunk_bytes": control_tts_chunk_bytes(),
        "chunk_bytes_env": os.getenv(CONTROL_TTS_CHUNK_BYTES_ENV, ""),
        "start_delay_seconds": control_tts_start_delay_seconds(),
        "start_delay_env": os.getenv(CONTROL_TTS_START_DELAY_ENV, ""),
        "pace_ratio": control_tts_chunk_pace_ratio(),
        "pace_ratio_env": os.getenv(CONTROL_TTS_CHUNK_PACE_RATIO_ENV, ""),
        "playback_mode_expected": "buffered_after_stream_end",
    })
    return settings


def pcm_stream_chunk_duration_seconds(pcm_stream: TtsPcmStream, chunk_bytes: int) -> float:
    bytes_per_frame = pcm_stream.channels * 2
    if pcm_stream.sample_rate <= 0 or bytes_per_frame <= 0 or chunk_bytes <= 0:
        return 0.0
    return chunk_bytes / bytes_per_frame / pcm_stream.sample_rate


def _initial_audio_stats() -> dict:
    return {
        "format": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "chunks": 0,
        "bytes": 0,
        "latest_chunk_bytes": 0,
        "latest_file_bytes": 0,
        "latest_file_max_bytes": audio_latest_pcm_max_bytes,
        "latest_window": None,
        "last_chunk_id": None,
        "last_meta": None,
        "updated_at": None,
    }


audio_runtime_stats = _initial_audio_stats()


def set_video_frame_source(source):
    global video_frame_source
    video_frame_source = source


def reset_state_for_tests() -> None:
    """Clear in-memory server state between integration tests."""

    global ws_state
    sessions.clear()
    recent_robot_events.clear()
    for waiter in list(audio_playback_waiters):
        if not waiter.done():
            waiter.cancel()
    audio_playback_waiters.clear()
    set_video_frame_source(None)
    video_observer_queues.clear()
    reset_audio_runtime_stats()
    ws_state = _empty_ws_state()


def reset_audio_runtime_stats() -> None:
    """Reset in-memory audio counters used by /audio observability."""

    global audio_runtime_stats
    audio_runtime_stats = _initial_audio_stats()


def _audio_latest_pcm_path() -> Path:
    return audio_runtime_dir / "latest_audio.pcm"


def _audio_stats_path() -> Path:
    return audio_runtime_dir / "audio_stats.json"


def _clamp_number(value, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _clamp_motion_speed(value, default: float, minimum: float, maximum: float) -> float:
    speed = _clamp_number(value, default, 0.0, maximum)
    if speed <= 0.0:
        return 0.0
    return max(minimum, speed)


def _clamp_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _safe_motion_payload(action: MotionAction, payload: dict) -> tuple[dict, int]:
    raw_params = payload.get("params", {})
    if not isinstance(raw_params, dict):
        raw_params = {}

    bench = bool(payload.get("bench"))
    max_speed = BENCH_MAX_SPEED if bench else MAX_SAFE_SPEED
    min_speed = 0.0 if bench else MIN_SAFE_SPEED
    max_timeout = BENCH_MAX_TIMEOUT_MS if bench else MAX_SAFE_TIMEOUT_MS
    max_distance = BENCH_MAX_DISTANCE_CM if bench else MAX_SAFE_DISTANCE_CM
    max_duration = BENCH_MAX_DURATION_MS if bench else MAX_SAFE_TIMEOUT_MS
    default_timeout = max_timeout if bench else DEFAULT_SAFE_TIMEOUT_MS

    timeout_ms = _clamp_int(
        payload.get("timeout_ms"),
        default_timeout,
        1,
        max_timeout,
    )

    if action == MotionAction.MOVE_OUT_OF_DOCK:
        params: dict = {}
        if raw_params.get("speed") is not None:
            params["speed"] = _clamp_motion_speed(raw_params.get("speed"), DEFAULT_SAFE_SPEED, min_speed, max_speed)
        elif not bench:
            params["speed"] = DEFAULT_SAFE_SPEED
        if raw_params.get("duration_ms") is not None:
            params["duration_ms"] = _clamp_int(raw_params.get("duration_ms"), max_duration, 1, max_duration)
        distance_value = raw_params.get("distance_cm", raw_params.get("distance"))
        if distance_value is not None:
            params["distance_cm"] = _clamp_number(
                distance_value,
                max_distance,
                0.0,
                max_distance,
            )
        elif not bench:
            params["distance_cm"] = DEFAULT_SAFE_DISTANCE_CM
        return params, timeout_ms

    if action == MotionAction.MOVE_BACK_TO_DOCK:
        params = {}
        if raw_params.get("speed") is not None:
            params["speed"] = _clamp_motion_speed(raw_params.get("speed"), DEFAULT_SAFE_SPEED, min_speed, max_speed)
        elif not bench:
            params["speed"] = DEFAULT_SAFE_SPEED
        if raw_params.get("duration_ms") is not None:
            params["duration_ms"] = _clamp_int(raw_params.get("duration_ms"), max_duration, 1, max_duration)
        return params, timeout_ms

    if action == MotionAction.TURN:
        params = {}
        if raw_params.get("speed") is not None:
            params["speed"] = _clamp_motion_speed(raw_params.get("speed"), DEFAULT_SAFE_SPEED, min_speed, max_speed)
        elif not bench:
            params["speed"] = DEFAULT_SAFE_SPEED
        angle_value = raw_params.get("angle_deg", raw_params.get("angle"))
        if angle_value is not None:
            params["angle_deg"] = _clamp_number(angle_value, 0.0, -360.0, 360.0)
        if raw_params.get("duration_ms") is not None:
            params["duration_ms"] = _clamp_int(raw_params.get("duration_ms"), max_duration, 1, max_duration)
        return params, timeout_ms

    if action == MotionAction.MOTOR_RAW:
        params = {
            "l_in1": _clamp_int(raw_params.get("l_in1"), 0, 0, 255),
            "l_in2": _clamp_int(raw_params.get("l_in2"), 0, 0, 255),
            "r_in1": _clamp_int(raw_params.get("r_in1"), 0, 0, 255),
            "r_in2": _clamp_int(raw_params.get("r_in2"), 0, 0, 255),
            "duration_ms": _clamp_int(
                raw_params.get("duration_ms"),
                800,
                1,
                BENCH_MAX_DURATION_MS,
            ),
        }
        return params, BENCH_MAX_TIMEOUT_MS

    return raw_params, int(payload.get("timeout_ms", 5000) or 5000)


def _write_audio_stats() -> None:
    try:
        audio_runtime_dir.mkdir(parents=True, exist_ok=True)
        _audio_stats_path().write_text(
            json.dumps(audio_runtime_stats, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write audio stats: %s", exc)


def _trim_latest_audio_file(path: Path) -> int:
    try:
        size = path.stat().st_size
    except OSError:
        return 0

    if size <= audio_latest_pcm_max_bytes:
        return size

    try:
        data = path.read_bytes()[-audio_latest_pcm_max_bytes:]
        path.write_bytes(data)
        return len(data)
    except OSError as exc:
        logger.warning("Failed to trim latest audio PCM: %s", exc)
        return size


def record_audio_chunk(pcm_frame: bytes) -> None:
    """Persist one PCM chunk and update bounded runtime observability stats."""

    if not pcm_frame:
        return

    audio_runtime_stats["chunks"] += 1
    audio_runtime_stats["bytes"] += len(pcm_frame)
    audio_runtime_stats["latest_chunk_bytes"] = len(pcm_frame)
    audio_runtime_stats["updated_at"] = time.time()
    ws_state.setdefault("counters", {})["audio_chunks"] = int(
        ws_state.setdefault("counters", {}).get("audio_chunks", 0)
    ) + 1

    try:
        audio_runtime_dir.mkdir(parents=True, exist_ok=True)
        latest_path = _audio_latest_pcm_path()
        with latest_path.open("ab") as pcm_file:
            pcm_file.write(pcm_frame)
        audio_runtime_stats["latest_file_bytes"] = _trim_latest_audio_file(latest_path)
        audio_runtime_stats["latest_window"] = pcm_s16le_stats(
            latest_path.read_bytes(),
            sample_rate=audio_runtime_stats["sample_rate"],
            channels=audio_runtime_stats["channels"],
        )
    except OSError as exc:
        logger.warning("Failed to write latest audio PCM: %s", exc)
    except ValueError as exc:
        logger.warning("Failed to analyze latest audio PCM: %s", exc)

    _write_audio_stats()
    write_ws_state_snapshot()


def record_audio_chunk_meta(payload: dict) -> None:
    """Record the latest audio.chunk_meta message sent on /control."""

    audio_runtime_stats["last_chunk_id"] = payload.get("chunk_id")
    audio_runtime_stats["last_meta"] = dict(payload)
    audio_runtime_stats["updated_at"] = time.time()
    _write_audio_stats()


def record_robot_event(event_type: str, payload: dict, device_id: Optional[str] = None) -> None:
    """Keep a bounded in-memory event trail for demo acceptance checks."""

    event_payload = dict(payload) if isinstance(payload, dict) else {}
    event_device_id = device_id or event_payload.get("device_id")
    event = {
        "type": event_type,
        "device_id": event_device_id,
        "recorded_at": time.time(),
        "payload": event_payload,
    }
    recent_robot_events.append(event)
    if event_type == "audio.playback_done":
        for waiter in list(audio_playback_waiters):
            if not waiter.done():
                waiter.set_result(dict(event))


def _audio_playback_done_matches(event: dict[str, Any], device_id: str, since: float) -> bool:
    if event.get("type") != "audio.playback_done":
        return False
    if event.get("device_id") != device_id:
        return False
    if float(event.get("recorded_at") or 0.0) < since:
        return False
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return payload.get("command_type") in {None, MessageType.AUDIO_PLAY_TTS.value}


async def wait_for_audio_playback_done(
    *,
    device_id: str,
    since: float,
    timeout_sec: float,
) -> dict[str, Any]:
    """Wait until the robot reports streamed TTS playback completion."""

    for event in reversed(recent_robot_events):
        if _audio_playback_done_matches(event, device_id, since):
            return dict(event)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for audio.playback_done from {device_id}")
        waiter = loop.create_future()
        audio_playback_waiters.add(waiter)
        try:
            event = await asyncio.wait_for(waiter, timeout=remaining)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"Timed out waiting for audio.playback_done from {device_id}") from exc
        finally:
            audio_playback_waiters.discard(waiter)
        if _audio_playback_done_matches(event, device_id, since):
            return dict(event)


def _is_local_observer_client(websocket: ServerConnection) -> bool:
    remote = getattr(websocket, "remote_address", None)
    if remote is None:
        return True
    host = remote[0] if isinstance(remote, tuple) and remote else remote
    return str(host) in {"127.0.0.1", "::1", "localhost"}


def publish_video_observer_packet(packet: bytes) -> None:
    """Fan out one validated /video packet to local observer queues."""

    for queue in list(video_observer_queues):
        while queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            queue.put_nowait(packet)
        except asyncio.QueueFull:
            logger.debug("Dropped /video observer frame for a slow subscriber")


def session_snapshot(now: Optional[float] = None) -> list[dict]:
    """Return JSON-safe session state for operator and preflight checks."""

    now = time.time() if now is None else now
    snapshots = []
    for device_id, session in sessions.items():
        item = {
            "device_id": device_id,
            "session_id": session.get("session_id"),
            "last_heartbeat_age_sec": max(0.0, now - float(session.get("last_hb", now))),
            "battery": session.get("battery"),
            "ip": session.get("ip"),
            "wifi_rssi": session.get("wifi_rssi"),
            "reset_reason": session.get("reset_reason"),
            "free_heap": session.get("free_heap"),
        }
        if "status" in session:
            item["status"] = session["status"]
        snapshots.append(item)
    return snapshots


def query_recent_robot_events(payload: dict) -> list[dict]:
    """Filter recent robot events by time, device, and event type."""

    since = payload.get("since")
    device_id = payload.get("device_id")
    event_type = payload.get("event_type")
    try:
        since_value = float(since) if since is not None else None
    except (TypeError, ValueError):
        since_value = None

    events = []
    for event in recent_robot_events:
        if since_value is not None and event.get("recorded_at", 0.0) < since_value:
            continue
        if device_id and event.get("device_id") != device_id:
            continue
        if event_type and event.get("type") != event_type:
            continue
        events.append(dict(event))
    return events


def remove_session_if_current(device_id: str, websocket: ServerConnection) -> bool:
    """Remove a robot session only if it still points at this connection."""

    session = sessions.get(device_id)
    if session and session.get("ws") is websocket:
        del sessions[device_id]
        write_ws_state_snapshot()
        return True
    return False


async def handle_control(websocket: ServerConnection):
    """Handle /control channel: bidirectional JSON messages."""
    device_id: Optional[str] = None
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON, ignoring")
                continue

            raw_type = data.get("type")
            payload = data.get("payload", {})
            if raw_type == "command.ack":
                record_ws_event(raw_type, payload, device_id=payload.get("device_id") or device_id)
                record_robot_event(raw_type, payload, device_id=device_id)
                logger.info(
                    "Command ack: type=%s status=%s",
                    payload.get("command_type"),
                    payload.get("status"),
                )
                continue

            if raw_type == "audio.playback_done":
                record_ws_event(raw_type, payload, device_id=payload.get("device_id") or device_id)
                record_robot_event(raw_type, payload, device_id=device_id)
                logger.info(
                    "Audio playback done: status=%s bytes_written=%s duration_ms=%s playback_mode=%s buffered_bytes=%s",
                    payload.get("status"),
                    payload.get("bytes_written"),
                    payload.get("duration_ms"),
                    payload.get("playback_mode"),
                    payload.get("buffered_bytes"),
                )
                continue

            if raw_type == "video.frame_meta":
                record_ws_event(raw_type, payload, device_id=payload.get("device_id") or device_id)
                logger.info(
                    "Video meta: frame_id=%s %sx%s",
                    payload.get("frame_id"),
                    payload.get("width"),
                    payload.get("height"),
                )
                continue

            if raw_type == "video.frame":
                frame_data = payload.get("data", "")
                record_ws_event(raw_type, {
                    "device_id": payload.get("device_id") or device_id,
                    "frame_id": payload.get("frame_id"),
                    "bytes": len(frame_data) if isinstance(frame_data, str) else 0,
                }, device_id=payload.get("device_id") or device_id)
                logger.info(
                    "Video frame base64: frame_id=%s bytes=%s",
                    payload.get("frame_id"),
                    len(frame_data) if isinstance(frame_data, str) else 0,
                )
                continue

            if raw_type == "audio.chunk_meta":
                record_audio_chunk_meta(payload)
                record_ws_event(raw_type, payload, device_id=payload.get("device_id") or device_id)
                record_robot_event(raw_type, payload, device_id=device_id)
                logger.info(
                    "Audio meta: chunk_id=%s format=%s sample_rate=%s channels=%s",
                    payload.get("chunk_id"),
                    payload.get("format"),
                    payload.get("sample_rate"),
                    payload.get("channels"),
                )
                continue

            if raw_type == "asr.transcript.mock":
                logger.info("ASR mock transcript: %s", payload.get("text"))
                continue

            try:
                msg_type, payload = parse_message(data)
            except ValueError as e:
                logger.warning(f"Unknown message type: {e}")
                continue

            if msg_type == MessageType.DEVICE_HELLO:
                device_id = payload.get("device_id", f"unknown-{uuid.uuid4().hex[:6]}")
                session_id = uuid.uuid4().hex[:12]
                sessions[device_id] = {
                    "device_id": device_id,
                    "ws": websocket,
                    "session_id": session_id,
                    "last_hb": time.time(),
                    "battery": payload.get("battery", 100),
                    "ip": payload.get("ip"),
                    "wifi_rssi": payload.get("wifi_rssi"),
                    "reset_reason": payload.get("reset_reason"),
                    "reset_reason_code": payload.get("reset_reason_code"),
                    "free_heap": payload.get("free_heap"),
                }
                logger.info(
                    "Robot connected: %s ip=%s rssi=%s reset=%s heap=%s (session %s)",
                    device_id,
                    payload.get("ip") or "-",
                    payload.get("wifi_rssi", "-"),
                    payload.get("reset_reason", "-"),
                    payload.get("free_heap", "-"),
                    session_id,
                )
                record_robot_event(MessageType.DEVICE_HELLO.value, payload, device_id=device_id)
                record_ws_event(raw_type, payload, device_id=device_id)
                welcome = make_welcome(session_id)
                await websocket.send(json.dumps(welcome, ensure_ascii=False))

            elif msg_type == MessageType.DEVICE_HEARTBEAT:
                if device_id and device_id in sessions:
                    sessions[device_id]["last_hb"] = time.time()
                    sessions[device_id]["battery"] = payload.get("battery", 0)
                    for key in ("charging", "docked", "wifi_rssi", "free_heap", "reset_reason"):
                        if key in payload:
                            sessions[device_id][key] = payload.get(key)
                    logger.debug(f"Heartbeat from {device_id}, battery={payload.get('battery')}%")
                record_ws_event(raw_type, payload, device_id=device_id or payload.get("device_id"))

            elif msg_type == MessageType.DEVICE_STATUS:
                if device_id and device_id in sessions:
                    sessions[device_id]["last_hb"] = time.time()
                    sessions[device_id]["status"] = payload
                    for key in ("battery", "charging", "docked", "wifi_rssi", "free_heap", "reset_reason"):
                        if key in payload:
                            sessions[device_id][key] = payload.get(key)
                record_robot_event(MessageType.DEVICE_STATUS.value, payload, device_id=device_id)
                logger.info(
                    "Robot status: expression=%s motion=%s camera=%s docked=%s",
                    payload.get("expression"),
                    payload.get("motion"),
                    payload.get("camera"),
                    payload.get("docked"),
                )
                record_ws_event(raw_type, payload, device_id=device_id or payload.get("device_id"))

            elif msg_type == MessageType.MOTION_COMPLETED:
                action_id = payload.get("action_id")
                result = payload.get("result")
                record_robot_event(MessageType.MOTION_COMPLETED.value, payload, device_id=device_id)
                logger.info(f"Motion completed: {action_id} -> {result}")
                record_ws_event(raw_type, payload, device_id=device_id or payload.get("device_id"))
                # TODO: notify agent/gateway that action finished

            elif msg_type == MessageType.ERROR_REPORT:
                record_robot_event(MessageType.ERROR_REPORT.value, payload, device_id=device_id)
                logger.warning(f"Robot error [{payload.get('code')}]: {payload.get('message')}")
                record_ws_event(raw_type, payload, device_id=device_id or payload.get("device_id"))

    except ConnectionClosed:
        logger.info(f"Robot disconnected: {device_id}")
    finally:
        if device_id:
            remove_session_if_current(device_id, websocket)


async def send_to_robot(message: dict, device_id: Optional[str] = None) -> tuple[bool, Optional[str], Optional[str]]:
    """Send a protocol message to a connected robot.

    If device_id is omitted, the first online robot session is used. The return
    value is (ok, selected_device_id, error_message).
    """

    if device_id:
        session = sessions.get(device_id)
        if not session:
            return False, None, f"Robot is not online: {device_id}"
    else:
        try:
            selected_device_id, session = next(iter(sessions.items()))
        except StopIteration:
            return False, None, "No online robot connected on /control"
        device_id = selected_device_id

    try:
        await session["ws"].send(json.dumps(message, ensure_ascii=False))
    except ConnectionClosed:
        remove_session_if_current(device_id, session["ws"])
        return False, device_id, f"Robot connection is closed: {device_id}"
    except Exception as exc:
        return False, device_id, f"Failed to send message to robot {device_id}: {exc}"

    return True, device_id, None


async def stream_control_binary_to_robot(
    pcm_stream: TtsPcmStream,
    device_id: str,
    *,
    pace_ratio: float | None = None,
) -> tuple[bool, Optional[str]]:
    """Send synthesized PCM bytes to the robot on the existing /control socket."""

    session = sessions.get(device_id)
    if not session:
        return False, f"Robot is not online: {device_id}"

    websocket = session["ws"]
    try:
        start_delay_seconds = control_tts_start_delay_seconds()
        chunk_bytes = control_tts_chunk_bytes()
        resolved_pace_ratio = pace_ratio if pace_ratio is not None else control_tts_chunk_pace_ratio()
        await asyncio.sleep(start_delay_seconds)
        for offset in range(0, len(pcm_stream.pcm), chunk_bytes):
            chunk = pcm_stream.pcm[offset:offset + chunk_bytes]
            await websocket.send(chunk)
            await asyncio.sleep(
                pcm_stream_chunk_duration_seconds(pcm_stream, len(chunk))
                * resolved_pace_ratio
            )
        await websocket.send(json.dumps(make_audio_stream_end(pcm_stream.audio_id), ensure_ascii=False))
    except ConnectionClosed:
        remove_session_if_current(device_id, websocket)
        return False, f"Robot connection is closed: {device_id}"
    except Exception as exc:
        return False, f"Failed to stream TTS audio to robot {device_id}: {exc}"

    return True, None


def build_robot_message(command_payload: dict) -> dict:
    """Convert a local agent.command payload into a robot protocol message."""

    command = command_payload.get("command")
    if command == MessageType.DISPLAY_EXPRESSION.value:
        expression = Expression(command_payload.get("expression", Expression.CARING.value))
        return make_expression(
            expression,
            duration_ms=int(command_payload.get("duration_ms", 3000)),
            loop=bool(command_payload.get("loop", False)),
        )

    if command == MessageType.MOTION_EXECUTE.value:
        action = MotionAction(command_payload.get("action", MotionAction.STOP.value))
        params, timeout_ms = _safe_motion_payload(action, command_payload)
        return make_motion(
            action_id=command_payload.get("action_id", f"agent-{uuid.uuid4().hex[:8]}"),
            action=action,
            params=params,
            timeout_ms=timeout_ms,
        )

    if command == MessageType.AUDIO_PLAY_TTS.value:
        text = command_payload.get("text", "")
        audio_id = command_payload.get("audio_id", f"tts-{uuid.uuid4().hex[:8]}")
        return make_play_tts(
            audio_id=audio_id,
            audio_url=command_payload.get("audio_url", f"mock://tts/{audio_id}"),
            duration_ms=int(command_payload.get("duration_ms", max(1000, len(text) * 180))),
            text_preview=text,
        )

    if command == MessageType.AUDIO_PLAY_LOCAL.value:
        return make_play_local(
            sound=command_payload.get("sound", "care_01"),
            volume=float(command_payload.get("volume", 0.7)),
        )

    raise ValueError(f"Unsupported agent command: {command}")


def build_tts_robot_message(pcm_stream: TtsPcmStream, *, playback_mode: str | None = None) -> dict:
    message = make_play_tts(
        audio_id=pcm_stream.audio_id,
        audio_url=f"stream://control/{pcm_stream.audio_id}",
        duration_ms=pcm_stream.duration_ms,
        text_preview=pcm_stream.text_preview,
        audio_format="pcm_s16le",
        sample_rate=pcm_stream.sample_rate,
        channels=pcm_stream.channels,
    )
    if playback_mode in {"buffered", "streaming"}:
        message.setdefault("payload", {})["playback_mode"] = playback_mode
    return message


async def synthesize_tts_pcm_stream_async(text: str) -> TtsPcmStream:
    """Run potentially slow external TTS synthesis without blocking /control."""

    started = time.monotonic()
    logger.info("TTS synthesis start text_chars=%s", len(text or ""))
    try:
        stream = await asyncio.to_thread(synthesize_tts_pcm_stream, text)
    except Exception:
        logger.exception("TTS synthesis failed after %.2fs", time.monotonic() - started)
        raise
    logger.info(
        "TTS synthesis done audio_id=%s pcm_bytes=%s duration_ms=%s elapsed_sec=%.2f",
        stream.audio_id,
        len(stream.pcm),
        stream.duration_ms,
        time.monotonic() - started,
    )
    return stream


async def send_agent_ack(
    websocket: ServerConnection,
    ok: bool,
    device_id: Optional[str] = None,
    forwarded_type: Optional[str] = None,
    error: Optional[str] = None,
    playback_done: Optional[dict[str, Any]] = None,
) -> None:
    """Send a small ack message back to the local /agent client."""

    payload = {"ok": ok}
    if ok:
        payload["device_id"] = device_id
        payload["forwarded_type"] = forwarded_type
        if playback_done is not None:
            payload["playback_done"] = playback_done
    else:
        payload["error"] = error or "Unknown error"

    await websocket.send(json.dumps({
        "type": "agent.ack",
        "payload": payload,
    }, ensure_ascii=False))


async def send_agent_state(websocket: ServerConnection) -> None:
    now = time.time()
    await websocket.send(json.dumps({
        "type": "agent.state",
        "payload": {
            "server_time": now,
            "sessions": session_snapshot(now),
        },
    }, ensure_ascii=False))


async def send_agent_events(websocket: ServerConnection, query_payload: dict) -> None:
    await websocket.send(json.dumps({
        "type": "agent.events",
        "payload": {
            "server_time": time.time(),
            "events": query_recent_robot_events(query_payload),
        },
    }, ensure_ascii=False))


async def handle_agent(websocket: ServerConnection):
    """Handle local Agent commands and forward them to the online robot."""

    logger.info("Agent command channel connected")
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
                msg_type = data.get("type")
                payload = data.get("payload", {})

                if msg_type == "agent.query":
                    query_name = payload.get("query", "state")
                    if query_name == "state":
                        await send_agent_state(websocket)
                    elif query_name == "recent_events":
                        await send_agent_events(websocket, payload)
                    else:
                        await send_agent_ack(websocket, ok=False, error=f"Unsupported agent query: {query_name}")
                    continue

                if msg_type != "agent.command":
                    raise ValueError(f"Unsupported message type: {data.get('type')}")

                device_id = payload.get("device_id")
                tts_stream = None
                tts_command_started_at = time.time()
                playback_done = None
                ws_state.setdefault("counters", {})["agent_commands"] = int(
                    ws_state.setdefault("counters", {}).get("agent_commands", 0)
                ) + 1
                write_ws_state_snapshot()
                playback_mode = None
                if (
                    payload.get("command") == MessageType.AUDIO_PLAY_TTS.value
                    and control_tts_stream_enabled()
                ):
                    tts_stream = await synthesize_tts_pcm_stream_async(payload.get("text", ""))
                    playback_mode = payload.get("playback_mode")
                    robot_message = build_tts_robot_message(
                        tts_stream,
                        playback_mode=playback_mode if playback_mode in {"buffered", "streaming"} else None,
                    )
                else:
                    robot_message = build_robot_message(payload)
                ok, selected_device_id, error = await send_to_robot(robot_message, device_id=device_id)
                if ok and tts_stream is not None and selected_device_id is not None:
                    ok, error = await stream_control_binary_to_robot(
                        tts_stream,
                        selected_device_id,
                        pace_ratio=1.0 if playback_mode == "streaming" else None,
                    )
                    if ok and control_tts_playback_done_required():
                        try:
                            playback_done_event = await wait_for_audio_playback_done(
                                device_id=selected_device_id,
                                since=tts_command_started_at,
                                timeout_sec=control_tts_playback_timeout_seconds(tts_stream),
                            )
                        except TimeoutError as exc:
                            ok = False
                            error = str(exc)
                        else:
                            playback_done = playback_done_event.get("payload")
                            if isinstance(playback_done, dict) and playback_done.get("status") != "ok":
                                ok = False
                                error = f"audio.playback_done status={playback_done.get('status')}"
                if ok:
                    await send_agent_ack(
                        websocket,
                        ok=True,
                        device_id=selected_device_id,
                        forwarded_type=robot_message.get("type"),
                        playback_done=playback_done,
                    )
                else:
                    await send_agent_ack(websocket, ok=False, error=error)
            except json.JSONDecodeError:
                await send_agent_ack(websocket, ok=False, error="Invalid JSON")
            except (TypeError, ValueError) as exc:
                await send_agent_ack(websocket, ok=False, error=str(exc))
            except RuntimeError as exc:
                await send_agent_ack(websocket, ok=False, error=str(exc))
    except ConnectionClosed:
        logger.info("Agent command channel disconnected")


async def handle_audio(websocket: ServerConnection):
    """Handle /audio channel: receive raw PCM frames from robot."""
    logger.info("Audio stream connected")
    try:
        async for frame in websocket:
            if isinstance(frame, bytes):
                record_audio_chunk(frame)
                logger.debug(
                    "Audio chunk: bytes=%s total_chunks=%s total_bytes=%s",
                    len(frame),
                    audio_runtime_stats["chunks"],
                    audio_runtime_stats["bytes"],
                )
    except ConnectionClosed:
        logger.info("Audio stream disconnected")


async def handle_video(websocket: ServerConnection):
    """Handle /video channel: receive JPEG frames from robot."""
    logger.info("Video stream connected")
    latest_path = None
    pending_header: Optional[tuple[int, int]] = None

    async def process_video_packet(packet: bytes) -> None:
        if len(packet) < 8:
            logger.warning("Invalid /video frame: packet shorter than header")
            return

        length = int.from_bytes(packet[0:4], "big")
        timestamp = int.from_bytes(packet[4:8], "big")
        jpeg_data = packet[8:8 + length]
        if len(jpeg_data) != length:
            logger.warning("Invalid /video frame: JPEG payload length does not match header")
            return

        logger.debug("Video frame: %s bytes, ts=%s", length, timestamp)
        publish_video_observer_packet(packet)

        if latest_path and jpeg_data:
            try:
                latest_path.write_bytes(jpeg_data)
                record_ws_event("video.frame", {
                    "bytes": len(jpeg_data),
                    "timestamp": timestamp,
                    "path": str(latest_path),
                })
            except OSError as exc:
                logger.warning("Failed to write latest video frame: %s", exc)

        if video_frame_source is not None:
            try:
                decoded = await video_frame_source.push_packet(packet)
                logger.debug(
                    "Decoded /video frame: frame_id=%s size=%sx%s",
                    decoded.get("frame_id"),
                    decoded.get("width"),
                    decoded.get("height"),
                )
            except VideoFrameDecodeError as exc:
                logger.warning("Invalid /video frame: %s", exc)
            except Exception:
                logger.exception("Unexpected error while processing /video frame")

    try:
        from pathlib import Path

        latest_path = Path("runtime") / "latest.jpg"
        latest_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        latest_path = None

    try:
        async for frame in websocket:
            if not isinstance(frame, bytes):
                continue

            if pending_header is not None:
                expected_length, timestamp = pending_header
                pending_header = None
                packet = (
                    expected_length.to_bytes(4, "big")
                    + timestamp.to_bytes(4, "big")
                    + frame[:expected_length]
                )
                await process_video_packet(packet)
                continue

            if len(frame) == 8:
                length = int.from_bytes(frame[0:4], "big")
                timestamp = int.from_bytes(frame[4:8], "big")
                pending_header = (length, timestamp)
                continue

            await process_video_packet(frame)
    except ConnectionClosed:
        logger.info("Video stream disconnected")


async def handle_video_observer(websocket: ServerConnection):
    """Local-only observer stream for decoded runtime consumers."""

    if not _is_local_observer_client(websocket):
        logger.warning("Rejected non-local /video-observer client: %s", getattr(websocket, "remote_address", None))
        await websocket.close(1008, "Local observer only")
        return

    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
    video_observer_queues.add(queue)
    logger.info("Video observer connected")
    try:
        while True:
            packet_task = asyncio.create_task(queue.get())
            closed_task = asyncio.create_task(websocket.wait_closed())
            done, pending = await asyncio.wait(
                {packet_task, closed_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if closed_task in done:
                break
            packet = packet_task.result()
            await websocket.send(packet)
    except ConnectionClosed:
        logger.info("Video observer disconnected")
    finally:
        video_observer_queues.discard(queue)


async def router(websocket: ServerConnection):
    """Route incoming connections to the correct handler by path."""
    path = websocket.request.path
    logger.info(f"New connection on path: {path}")

    if path == "/control":
        await handle_control(websocket)
    elif path == "/agent":
        await handle_agent(websocket)
    elif path == "/audio":
        await handle_audio(websocket)
    elif path == "/video":
        await handle_video(websocket)
    elif path == "/video-observer":
        await handle_video_observer(websocket)
    else:
        logger.warning(f"Unknown path: {path}, closing")
        await websocket.close(1008, "Unknown path")


async def heartbeat_monitor():
    """Background task: disconnect robots that stop sending heartbeats."""
    while True:
        await asyncio.sleep(10)
        now = time.time()
        dead = [did for did, s in sessions.items() if now - s["last_hb"] > 30]
        for did in dead:
            logger.warning(f"Heartbeat timeout: {did}, closing session")
            try:
                await sessions[did]["ws"].close()
            except Exception:
                pass
            del sessions[did]
            write_ws_state_snapshot()


async def start_server(host: str = "0.0.0.0", port: int = 8765):
    """Start the WebSocket server and return the websockets server object."""

    logger.info(f"Starting Xiao An WebSocket server on {host}:{port}")
    return await serve(router, host, port)


async def main():
    server = await start_server("0.0.0.0", 8765)
    heartbeat_task = asyncio.create_task(heartbeat_monitor())
    try:
        await asyncio.Future()   # run forever
    finally:
        heartbeat_task.cancel()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
