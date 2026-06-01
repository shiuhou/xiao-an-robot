"""Integration tests for agent.core.gateway RobotGateway."""

from __future__ import annotations

import asyncio
import json
import unittest

try:
    import websockets
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None

from agent.core.gateway import RobotGateway

if websockets is not None:
    from base_station.ws_server import server as ws_server
else:  # pragma: no cover - import is skipped with the dependency
    ws_server = None


def build_message(msg_type: str, seq: int, payload: dict) -> str:
    return json.dumps({
        "type": msg_type,
        "ts": 1714537000000 + seq,
        "seq": seq,
        "payload": payload,
    }, ensure_ascii=False)


@unittest.skipIf(websockets is None, "websockets dependency is not installed")
class AgentGatewayTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ws_server.reset_state_for_tests()
        self.server = await ws_server.start_server("127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.robot = await asyncio.wait_for(
            websockets.connect(f"ws://127.0.0.1:{self.port}/control"),
            timeout=2,
        )
        self.gateway = RobotGateway(url=f"ws://127.0.0.1:{self.port}/agent", timeout_sec=2)

        await asyncio.wait_for(
            self.robot.send(build_message(
                "device.hello",
                1,
                {
                    "device_id": "gateway-test-robot",
                    "firmware": "integration-test",
                    "battery": 90,
                },
            )),
            timeout=2,
        )
        welcome = await self.recv_json(self.robot)
        self.assertEqual(welcome["type"], "system.welcome")

    async def asyncTearDown(self) -> None:
        if hasattr(self, "robot"):
            await self.robot.close()
        if hasattr(self, "server"):
            self.server.close()
            await self.server.wait_closed()
        ws_server.reset_state_for_tests()

    async def recv_json(self, websocket) -> dict:
        raw = await asyncio.wait_for(websocket.recv(), timeout=2)
        return json.loads(raw)

    async def test_send_expression_forwards_display_expression(self) -> None:
        ack_task = asyncio.create_task(self.gateway.send_expression("caring"))
        robot_message = await self.recv_json(self.robot)
        ack = await asyncio.wait_for(ack_task, timeout=2)

        self.assertEqual(robot_message["type"], "display.expression")
        self.assertEqual(robot_message["payload"]["expression"], "caring")
        self.assertTrue(ack["payload"]["ok"])
        self.assertEqual(ack["payload"]["forwarded_type"], "display.expression")

    async def test_send_motion_forwards_motion_execute(self) -> None:
        ack_task = asyncio.create_task(self.gateway.send_motion("move_out_of_dock"))
        robot_message = await self.recv_json(self.robot)
        ack = await asyncio.wait_for(ack_task, timeout=2)

        self.assertEqual(robot_message["type"], "motion.execute")
        self.assertEqual(robot_message["payload"]["action"], "move_out_of_dock")
        self.assertTrue(ack["payload"]["ok"])
        self.assertEqual(ack["payload"]["forwarded_type"], "motion.execute")

    async def test_send_tts_forwards_audio_play_tts(self) -> None:
        text = "你已经工作很久了，休息一下吧。"
        ack_task = asyncio.create_task(self.gateway.send_tts(text))
        robot_message = await self.recv_json(self.robot)
        ack = await asyncio.wait_for(ack_task, timeout=2)

        self.assertEqual(robot_message["type"], "audio.play_tts")
        self.assertEqual(robot_message["payload"]["text_preview"], text)
        self.assertTrue(ack["payload"]["ok"])
        self.assertEqual(ack["payload"]["forwarded_type"], "audio.play_tts")


if __name__ == "__main__":
    unittest.main()
