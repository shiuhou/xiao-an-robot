"""Integration tests for Agent -> BaseStation -> Robot command forwarding."""

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
        "ts": 1714536000000 + seq,
        "seq": seq,
        "payload": payload,
    }, ensure_ascii=False)


@unittest.skipIf(websockets is None, "websockets dependency is not installed")
class WebSocketCommandForwardingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ws_server.reset_state_for_tests()
        self.server = await ws_server.start_server("127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.robot = await asyncio.wait_for(
            websockets.connect(f"ws://127.0.0.1:{self.port}/control"),
            timeout=2,
        )
        self.agent = await asyncio.wait_for(
            websockets.connect(f"ws://127.0.0.1:{self.port}/agent"),
            timeout=2,
        )

        await asyncio.wait_for(
            self.robot.send(build_message(
                "device.hello",
                1,
                {
                    "device_id": "test-robot-001",
                    "firmware": "integration-test",
                    "battery": 88,
                },
            )),
            timeout=2,
        )
        welcome = await self.recv_json(self.robot)
        self.assertEqual(welcome["type"], "system.welcome")

    async def asyncTearDown(self) -> None:
        if hasattr(self, "agent"):
            await self.agent.close()
        if hasattr(self, "robot"):
            await self.robot.close()
        if hasattr(self, "server"):
            self.server.close()
            await self.server.wait_closed()
        ws_server.reset_state_for_tests()

    async def recv_json(self, websocket) -> dict:
        raw = await asyncio.wait_for(websocket.recv(), timeout=2)
        return json.loads(raw)

    async def send_agent_command_and_assert_forwarded(self, payload: dict, expected_forwarded_type: str) -> dict:
        await asyncio.wait_for(
            self.agent.send(json.dumps({
                "type": "agent.command",
                "payload": payload,
            }, ensure_ascii=False)),
            timeout=2,
        )

        robot_message = await self.recv_json(self.robot)
        self.assertEqual(robot_message["type"], expected_forwarded_type)

        ack = await self.recv_json(self.agent)
        self.assertEqual(ack["type"], "agent.ack")
        self.assertTrue(ack["payload"]["ok"])
        self.assertEqual(ack["payload"]["device_id"], "test-robot-001")
        self.assertEqual(ack["payload"]["forwarded_type"], expected_forwarded_type)
        return robot_message

    async def test_display_expression_command_is_forwarded(self) -> None:
        robot_message = await self.send_agent_command_and_assert_forwarded(
            {
                "command": "display.expression",
                "expression": "caring",
            },
            "display.expression",
        )

        self.assertEqual(robot_message["payload"]["expression"], "caring")

    async def test_motion_execute_command_is_forwarded(self) -> None:
        robot_message = await self.send_agent_command_and_assert_forwarded(
            {
                "command": "motion.execute",
                "action": "move_out_of_dock",
            },
            "motion.execute",
        )

        self.assertEqual(robot_message["payload"]["action"], "move_out_of_dock")
        self.assertIn("action_id", robot_message["payload"])

    async def test_audio_play_tts_command_is_forwarded(self) -> None:
        text = "你已经工作很久了，休息一下吧。"
        robot_message = await self.send_agent_command_and_assert_forwarded(
            {
                "command": "audio.play_tts",
                "text": text,
            },
            "audio.play_tts",
        )

        self.assertEqual(robot_message["payload"]["text_preview"], text)
        self.assertIn("audio_id", robot_message["payload"])
        self.assertIn("audio_url", robot_message["payload"])


if __name__ == "__main__":
    unittest.main()
