"""
server.py
---------
WebSocket server running on the Intel DK-2500 base station.
Handles three channels: /control /audio /video

Run with: python -m base_station.ws_server.server

Author: 张子尧
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from .protocol import MessageType, make_welcome, parse_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ws_server")

# Active robot sessions: device_id -> session dict
sessions: Dict[str, dict] = {}


async def handle_control(websocket: WebSocketServerProtocol):
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
                device_id  = payload.get("device_id", f"unknown-{uuid.uuid4().hex[:6]}")
                session_id = uuid.uuid4().hex[:12]
                sessions[device_id] = {
                    "ws":         websocket,
                    "session_id": session_id,
                    "last_hb":    time.time(),
                    "battery":    payload.get("battery", 100),
                }
                logger.info(f"Robot connected: {device_id} (session {session_id})")
                welcome = make_welcome(session_id)
                await websocket.send(json.dumps(welcome))

            elif msg_type == MessageType.DEVICE_HEARTBEAT:
                if device_id and device_id in sessions:
                    sessions[device_id]["last_hb"] = time.time()
                    sessions[device_id]["battery"] = payload.get("battery", 0)
                    logger.debug(f"Heartbeat from {device_id}, battery={payload.get('battery')}%")

            elif msg_type == MessageType.MOTION_COMPLETED:
                action_id = payload.get("action_id")
                result    = payload.get("result")
                logger.info(f"Motion completed: {action_id} -> {result}")
                # TODO: notify agent/gateway that action finished

            elif msg_type == MessageType.ERROR_REPORT:
                logger.warning(f"Robot error [{payload.get('code')}]: {payload.get('message')}")

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Robot disconnected: {device_id}")
    finally:
        if device_id and device_id in sessions:
            del sessions[device_id]


async def handle_audio(websocket: WebSocketServerProtocol):
    """Handle /audio channel: receive raw PCM frames from robot."""
    logger.info("Audio stream connected")
    try:
        async for frame in websocket:
            if isinstance(frame, bytes):
                # TODO: pipe PCM frames to VAD -> ASR pipeline
                pass
    except websockets.exceptions.ConnectionClosed:
        logger.info("Audio stream disconnected")


async def handle_video(websocket: WebSocketServerProtocol):
    """Handle /video channel: receive JPEG frames from robot."""
    logger.info("Video stream connected")
    try:
        async for frame in websocket:
            if isinstance(frame, bytes) and len(frame) > 8:
                # Parse 8-byte header: 4B length + 4B timestamp
                length    = int.from_bytes(frame[0:4], "big")
                timestamp = int.from_bytes(frame[4:8], "big")
                jpeg_data = frame[8:8 + length]
                # TODO: pipe jpeg_data to face emotion detection pipeline
                logger.debug(f"Video frame: {length} bytes, ts={timestamp}")
    except websockets.exceptions.ConnectionClosed:
        logger.info("Video stream disconnected")


async def router(websocket: WebSocketServerProtocol):
    """Route incoming connections to the correct handler by path."""
    path = websocket.request.path
    logger.info(f"New connection on path: {path}")

    if path == "/control":
        await handle_control(websocket)
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
        now  = time.time()
        dead = [did for did, s in sessions.items() if now - s["last_hb"] > 30]
        for did in dead:
            logger.warning(f"Heartbeat timeout: {did}, closing session")
            try:
                await sessions[did]["ws"].close()
            except Exception:
                pass
            del sessions[did]


async def main():
    logger.info("Starting Xiao An WebSocket server on 0.0.0.0:8765")
    async with websockets.serve(router, "0.0.0.0", 8765):
        await asyncio.gather(
            asyncio.Future(),   # run forever
            heartbeat_monitor(),
        )


if __name__ == "__main__":
    asyncio.run(main())
