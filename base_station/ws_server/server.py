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


def set_video_frame_source(source):
    global video_frame_source
    video_frame_source = source


def reset_state_for_tests() -> None:
    """Clear in-memory server state between integration tests."""

    sessions.clear()
    set_video_frame_source(None)


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

            elif raw.get("type") == "command.ack":
                logger.info(
                    "Command ack: type=%s status=%s",
                    payload.get("command_type"),
                    payload.get("status"),
                )

            elif raw.get("type") == "video.frame_meta":
                logger.info(
                    "Video meta: frame_id=%s %sx%s",
                    payload.get("frame_id"),
                    payload.get("width"),
                    payload.get("height"),
                )

            elif raw.get("type") == "video.frame":
                data = payload.get("data", "")
                logger.info(
                    "Video frame base64: frame_id=%s bytes=%s",
                    payload.get("frame_id"),
                    len(data) if isinstance(data, str) else 0,
                )

            elif raw.get("type") == "asr.transcript.mock":
                logger.info("ASR mock transcript: %s", payload.get("text"))

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
        return make_motion(
            action_id=command_payload.get("action_id", f"agent-{uuid.uuid4().hex[:8]}"),
            action=action,
            params=command_payload.get("params", {}),
            timeout_ms=int(command_payload.get("timeout_ms", 5000)),
        )

    if command == MessageType.AUDIO_PLAY_TTS.value:
        text = command_payload.get("text", "")
        audio_id = command_payload.get("audio_id", f"tts-{uuid.uuid4().hex[:8]}")
        return make_play_tts(
            audio_id=audio_id,
            audio_url=command_payload.get("audio_url", f"mock://tts/{audio_id}.mp3"),
            duration_ms=int(command_payload.get("duration_ms", max(1000, len(text) * 180))),
            text_preview=text,
        )

    if command == MessageType.AUDIO_PLAY_LOCAL.value:
        return make_play_local(
            sound=command_payload.get("sound", "wakeup_chime"),
            volume=float(command_payload.get("volume", 0.8)),
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
                # TODO: pipe PCM frames to VAD -> ASR pipeline
                pass
    except ConnectionClosed:
        logger.info("Audio stream disconnected")


async def handle_video(websocket: ServerConnection):
    """Handle /video channel: receive JPEG frames from robot."""
    logger.info("Video stream connected")
    latest_path = None
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

            if len(frame) > 8:
                length = int.from_bytes(frame[0:4], "big")
                timestamp = int.from_bytes(frame[4:8], "big")
                jpeg_data = frame[8:8 + length]
                logger.debug("Video frame: %s bytes, ts=%s", length, timestamp)

                if latest_path and jpeg_data:
                    try:
                        latest_path.write_bytes(jpeg_data)
                    except OSError as exc:
                        logger.warning("Failed to write latest video frame: %s", exc)

            if video_frame_source is not None:
                try:
                    decoded = await video_frame_source.push_packet(frame)
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
