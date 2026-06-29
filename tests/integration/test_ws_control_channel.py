"""Integration tests for the base station WebSocket /control channel."""

from __future__ import annotations

import asyncio
import json
import unittest

try:
    import websockets
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None

if websockets is not None:
    from base_station.ws_server import server as ws_server
else:  # pragma: no cover - import is skipped with the dependency
    ws_server = None


def build_message(msg_type: str, seq: int, payload: dict) -> str:
    return json.dumps({
        "type": msg_type,
        "ts": 1714539000000 + seq,
        "seq": seq,
        "payload": payload,
    }, ensure_ascii=False)


@unittest.skipIf(websockets is None, "websockets dependency is not installed")
class WebSocketControlChannelTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ws_server.reset_state_for_tests()
        self.server = await ws_server.start_server("127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.robot = await asyncio.wait_for(
            websockets.connect(f"ws://127.0.0.1:{self.port}/control"),
            timeout=2,
        )

    async def asyncTearDown(self) -> None:
        if hasattr(self, "robot"):
            await self.robot.close()
        if hasattr(self, "server"):
            self.server.close()
            await self.server.wait_closed()
        ws_server.reset_state_for_tests()

    async def recv_json(self) -> dict:
        raw = await asyncio.wait_for(self.robot.recv(), timeout=2)
        return json.loads(raw)

    async def send_hello(self, device_id: str = "control-test-robot") -> dict:
        await asyncio.wait_for(
            self.robot.send(build_message(
                "device.hello",
                1,
                {
                    "device_id": device_id,
                    "firmware": "control-test",
                    "battery": 91,
                    "ip": "192.168.137.42",
                    "wifi_rssi": -48,
                    "reset_reason": "poweron",
                    "reset_reason_code": 1,
                    "free_heap": 251000,
                },
            )),
            timeout=2,
        )
        return await self.recv_json()

    async def test_hello_receives_welcome_and_registers_session(self) -> None:
        welcome = await self.send_hello()

        self.assertEqual(welcome["type"], "system.welcome")
        self.assertIn("control-test-robot", ws_server.sessions)
        self.assertEqual(ws_server.sessions["control-test-robot"]["battery"], 91)
        self.assertEqual(ws_server.sessions["control-test-robot"]["ip"], "192.168.137.42")
        self.assertEqual(ws_server.sessions["control-test-robot"]["wifi_rssi"], -48)
        self.assertEqual(ws_server.sessions["control-test-robot"]["reset_reason"], "poweron")
        self.assertEqual(ws_server.sessions["control-test-robot"]["reset_reason_code"], 1)
        self.assertEqual(ws_server.sessions["control-test-robot"]["free_heap"], 251000)

    async def test_heartbeat_updates_session_after_invalid_json_is_ignored(self) -> None:
        await self.send_hello()

        await asyncio.wait_for(self.robot.send("{not-json"), timeout=2)
        await asyncio.wait_for(
            self.robot.send(build_message(
                "device.heartbeat",
                2,
                {
                    "device_id": "control-test-robot",
                    "battery": 87,
                    "uptime_sec": 5,
                    "wifi_rssi": -52,
                },
            )),
            timeout=2,
        )
        await asyncio.sleep(0.05)

        self.assertIn("control-test-robot", ws_server.sessions)
        self.assertEqual(ws_server.sessions["control-test-robot"]["battery"], 87)

    async def test_base64_video_messages_do_not_block_control_channel(self) -> None:
        await self.send_hello()

        await asyncio.wait_for(
            self.robot.send(build_message(
                "video.frame_meta",
                2,
                {
                    "device_id": "control-test-robot",
                    "format": "jpeg",
                    "width": 320,
                    "height": 240,
                    "frame_id": 1,
                },
            )),
            timeout=2,
        )
        await asyncio.wait_for(
            self.robot.send(build_message(
                "video.frame",
                3,
                {
                    "device_id": "control-test-robot",
                    "format": "jpeg_base64",
                    "width": 320,
                    "height": 240,
                    "frame_id": 1,
                    "data": "/9j/4AAQSkZJRg==",
                },
            )),
            timeout=2,
        )
        await asyncio.wait_for(
            self.robot.send(build_message(
                "device.heartbeat",
                4,
                {
                    "device_id": "control-test-robot",
                    "battery": 83,
                    "uptime_sec": 6,
                    "wifi_rssi": -54,
                },
            )),
            timeout=2,
        )
        await asyncio.sleep(0.05)

        self.assertIn("control-test-robot", ws_server.sessions)
        self.assertEqual(ws_server.sessions["control-test-robot"]["battery"], 83)


if __name__ == "__main__":
    unittest.main()
