"""WebSocket gateway from Agent code to the base station /agent route.

This module does not depend on OpenClaw, OpenVINO, ASR, TTS, or the database.
It only sends robot-control commands through the local base_station WebSocket
API and validates the returned agent.ack message.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


class RobotGatewayError(RuntimeError):
    """Raised when a robot command cannot be delivered through base_station."""


class RobotGateway:
    """Small client for sending Agent commands to base_station /agent."""

    def __init__(self, url: str = "ws://127.0.0.1:8765/agent", timeout_sec: float = 3.0):
        self.url = url
        self.timeout_sec = timeout_sec

    async def send_command(self, command: str, **payload: Any) -> dict:
        """Send an agent.command message and return a successful agent.ack."""

        try:
            import websockets
        except ImportError as exc:
            raise RobotGatewayError(
                "Missing dependency: websockets. Install agent or base_station requirements first."
            ) from exc

        message = {
            "type": "agent.command",
            "payload": {
                "command": command,
                **payload,
            },
        }

        websocket = None
        try:
            websocket = await asyncio.wait_for(websockets.connect(self.url), timeout=self.timeout_sec)
            await asyncio.wait_for(
                websocket.send(json.dumps(message, ensure_ascii=False)),
                timeout=self.timeout_sec,
            )
            raw_ack = await asyncio.wait_for(websocket.recv(), timeout=self.timeout_sec)
        except asyncio.TimeoutError as exc:
            raise RobotGatewayError(f"Timed out sending robot command to {self.url}") from exc
        except OSError as exc:
            raise RobotGatewayError(f"Failed to connect to base_station /agent at {self.url}: {exc}") from exc
        except Exception as exc:
            raise RobotGatewayError(f"Failed to send robot command through {self.url}: {exc}") from exc
        finally:
            if websocket is not None:
                await websocket.close()

        try:
            ack = json.loads(raw_ack)
        except json.JSONDecodeError as exc:
            raise RobotGatewayError(f"Invalid JSON ack from base_station: {raw_ack!r}") from exc

        payload = ack.get("payload")
        if not isinstance(payload, dict):
            raise RobotGatewayError(f"Invalid agent.ack payload: {ack!r}")

        if not payload.get("ok"):
            raise RobotGatewayError(payload.get("error", "base_station rejected robot command"))

        return ack

    async def send_expression(self, expression: str, duration_ms: int = 3000, loop: bool = False) -> dict:
        return await self.send_command(
            "display.expression",
            expression=expression,
            duration_ms=duration_ms,
            loop=loop,
        )

    async def send_motion(self, action: str, params: dict | None = None, timeout_ms: int = 5000) -> dict:
        return await self.send_command(
            "motion.execute",
            action=action,
            params=params or {},
            timeout_ms=timeout_ms,
        )

    async def send_tts(self, text: str) -> dict:
        return await self.send_command("audio.play_tts", text=text)

    async def send_local_audio(self, audio_id: str, audio_url: str | None = None) -> dict:
        payload: dict[str, Any] = {
            "audio_id": audio_id,
            "sound": audio_id,
        }
        if audio_url is not None:
            payload["audio_url"] = audio_url

        return await self.send_command("audio.play_local", **payload)


# Backward-compatible alias for older placeholder imports.
Gateway = RobotGateway
