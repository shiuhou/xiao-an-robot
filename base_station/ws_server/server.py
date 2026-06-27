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
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from base_station.perception.ws_video_source import VideoFrameDecodeError

from .protocol import (
    Expression,
    MessageType,
    MotionAction,
    make_expression,
    make_motion,
    make_play_local,
    make_play_tts,
    make_welcome,
    parse_message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ws_server")

# Active robot sessions: device_id -> session dict
sessions: Dict[str, dict] = {}
video_frame_source = None
audio_runtime_dir = Path("runtime")
audio_latest_pcm_max_bytes = 16000 * 2 * 5  # 5 seconds of 16kHz mono s16le PCM.
MIN_SAFE_SPEED = 0.52
MAX_SAFE_SPEED = 0.56
DEFAULT_SAFE_SPEED = 0.56
MAX_SAFE_DISTANCE_CM = 10.0
DEFAULT_SAFE_DISTANCE_CM = 10.0
MAX_SAFE_TIMEOUT_MS = 1200
DEFAULT_SAFE_TIMEOUT_MS = 1200
BENCH_MAX_SPEED = 1.0
BENCH_MAX_TIMEOUT_MS = 10000
BENCH_MAX_DISTANCE_CM = 100.0
BENCH_MAX_DURATION_MS = 10000


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

    sessions.clear()
    set_video_frame_source(None)
    reset_audio_runtime_stats()


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

    try:
        audio_runtime_dir.mkdir(parents=True, exist_ok=True)
        latest_path = _audio_latest_pcm_path()
        with latest_path.open("ab") as pcm_file:
            pcm_file.write(pcm_frame)
        audio_runtime_stats["latest_file_bytes"] = _trim_latest_audio_file(latest_path)
    except OSError as exc:
        logger.warning("Failed to write latest audio PCM: %s", exc)

    _write_audio_stats()


def record_audio_chunk_meta(payload: dict) -> None:
    """Record the latest audio.chunk_meta message sent on /control."""

    audio_runtime_stats["last_chunk_id"] = payload.get("chunk_id")
    audio_runtime_stats["last_meta"] = dict(payload)
    audio_runtime_stats["updated_at"] = time.time()
    _write_audio_stats()


def remove_session_if_current(device_id: str, websocket: ServerConnection) -> bool:
    """Remove a robot session only if it still points at this connection."""

    session = sessions.get(device_id)
    if session and session.get("ws") is websocket:
        del sessions[device_id]
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
                logger.info(
                    "Command ack: type=%s status=%s",
                    payload.get("command_type"),
                    payload.get("status"),
                )
                continue

            if raw_type == "video.frame_meta":
                logger.info(
                    "Video meta: frame_id=%s %sx%s",
                    payload.get("frame_id"),
                    payload.get("width"),
                    payload.get("height"),
                )
                continue

            if raw_type == "video.frame":
                frame_data = payload.get("data", "")
                logger.info(
                    "Video frame base64: frame_id=%s bytes=%s",
                    payload.get("frame_id"),
                    len(frame_data) if isinstance(frame_data, str) else 0,
                )
                continue

            if raw_type == "audio.chunk_meta":
                record_audio_chunk_meta(payload)
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
                }
                logger.info(f"Robot connected: {device_id} (session {session_id})")
                welcome = make_welcome(session_id)
                await websocket.send(json.dumps(welcome, ensure_ascii=False))

            elif msg_type == MessageType.DEVICE_HEARTBEAT:
                if device_id and device_id in sessions:
                    sessions[device_id]["last_hb"] = time.time()
                    sessions[device_id]["battery"] = payload.get("battery", 0)
                    logger.debug(f"Heartbeat from {device_id}, battery={payload.get('battery')}%")

            elif msg_type == MessageType.DEVICE_STATUS:
                if device_id and device_id in sessions:
                    sessions[device_id]["last_hb"] = time.time()
                    sessions[device_id]["status"] = payload
                logger.info(
                    "Robot status: expression=%s motion=%s camera=%s docked=%s",
                    payload.get("expression"),
                    payload.get("motion"),
                    payload.get("camera"),
                    payload.get("docked"),
                )

            elif msg_type == MessageType.MOTION_COMPLETED:
                action_id = payload.get("action_id")
                result = payload.get("result")
                logger.info(f"Motion completed: {action_id} -> {result}")
                # TODO: notify agent/gateway that action finished

            elif msg_type == MessageType.ERROR_REPORT:
                logger.warning(f"Robot error [{payload.get('code')}]: {payload.get('message')}")

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


async def send_agent_ack(
    websocket: ServerConnection,
    ok: bool,
    device_id: Optional[str] = None,
    forwarded_type: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Send a small ack message back to the local /agent client."""

    payload = {"ok": ok}
    if ok:
        payload["device_id"] = device_id
        payload["forwarded_type"] = forwarded_type
    else:
        payload["error"] = error or "Unknown error"

    await websocket.send(json.dumps({
        "type": "agent.ack",
        "payload": payload,
    }, ensure_ascii=False))


async def handle_agent(websocket: ServerConnection):
    """Handle local Agent commands and forward them to the online robot."""

    logger.info("Agent command channel connected")
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
                if data.get("type") != "agent.command":
                    raise ValueError(f"Unsupported message type: {data.get('type')}")

                payload = data.get("payload", {})
                device_id = payload.get("device_id")
                robot_message = build_robot_message(payload)
                ok, selected_device_id, error = await send_to_robot(robot_message, device_id=device_id)
                if ok:
                    await send_agent_ack(
                        websocket,
                        ok=True,
                        device_id=selected_device_id,
                        forwarded_type=robot_message.get("type"),
                    )
                else:
                    await send_agent_ack(websocket, ok=False, error=error)
            except json.JSONDecodeError:
                await send_agent_ack(websocket, ok=False, error="Invalid JSON")
            except (TypeError, ValueError) as exc:
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

        if latest_path and jpeg_data:
            try:
                latest_path.write_bytes(jpeg_data)
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
