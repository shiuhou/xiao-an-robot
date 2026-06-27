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

    async def send_agent_command_and_assert_forwarded(
        self,
        payload: dict,
        expected_forwarded_type: str,
    ) -> dict:
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
                "duration_ms": 3000,
                "loop": False,
            },
            "display.expression",
        )

        self.assertEqual(robot_message["payload"]["expression"], "caring")
        self.assertEqual(robot_message["payload"]["duration_ms"], 3000)
        self.assertFalse(robot_message["payload"]["loop"])

    async def test_motion_execute_command_is_forwarded(self) -> None:
        robot_message = await self.send_agent_command_and_assert_forwarded(
            {
                "command": "motion.execute",
                "action": "move_out_of_dock",
                "action_id": "agent-test-001",
            },
            "motion.execute",
        )

        self.assertEqual(robot_message["payload"]["action"], "move_out_of_dock")
        self.assertEqual(robot_message["payload"]["action_id"], "agent-test-001")
        self.assertEqual(robot_message["payload"]["params"], {
            "speed": 0.2,
            "distance_cm": 2.0,
        })
        self.assertEqual(robot_message["payload"]["timeout_ms"], 500)

    async def test_motion_execute_command_clamps_hardware_safety_params(self) -> None:
        robot_message = await self.send_agent_command_and_assert_forwarded(
            {
                "command": "motion.execute",
                "action": "move_out_of_dock",
                "params": {
                    "speed": 1.0,
                    "distance_cm": 99,
                },
                "timeout_ms": 10000,
            },
            "motion.execute",
        )

        self.assertEqual(robot_message["payload"]["params"], {
            "speed": 0.2,
            "distance_cm": 2.0,
        })
        self.assertEqual(robot_message["payload"]["timeout_ms"], 500)

    async def test_motion_bench_command_forwards_full_speed_and_timeout(self) -> None:
        robot_message = await self.send_agent_command_and_assert_forwarded(
            {
                "command": "motion.execute",
                "action": "move_out_of_dock",
                "bench": True,
                "params": {
                    "speed": 1.0,
                    "duration_ms": 5000,
                },
                "timeout_ms": 5000,
            },
            "motion.execute",
        )

        self.assertEqual(robot_message["payload"]["params"], {
            "speed": 1.0,
            "duration_ms": 5000,
        })
        self.assertEqual(robot_message["payload"]["timeout_ms"], 5000)

    async def test_motion_bench_turn_keeps_angle_duration_and_speed(self) -> None:
        robot_message = await self.send_agent_command_and_assert_forwarded(
            {
                "command": "motion.execute",
                "action": "turn",
                "bench": True,
                "params": {
                    "speed": 0.4,
                    "angle_deg": -30,
                    "duration_ms": 1200,
                },
                "timeout_ms": 1500,
            },
            "motion.execute",
        )

        self.assertEqual(robot_message["payload"]["params"], {
            "speed": 0.4,
            "angle_deg": -30.0,
            "duration_ms": 1200,
        })
        self.assertEqual(robot_message["payload"]["timeout_ms"], 1500)

    async def test_audio_play_local_commands_are_forwarded(self) -> None:
        for sound in ("care_01", "alarm_01", "wake_01"):
            with self.subTest(sound=sound):
                robot_message = await self.send_agent_command_and_assert_forwarded(
                    {
                        "command": "audio.play_local",
                        "sound": sound,
                        "volume": 0.7,
                    },
                    "audio.play_local",
                )

                self.assertEqual(robot_message["payload"]["sound"], sound)
                self.assertAlmostEqual(robot_message["payload"]["volume"], 0.7)

    async def test_audio_play_tts_command_is_forwarded_as_mock_tone(self) -> None:
        text = "hello xiao an"
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
        self.assertTrue(robot_message["payload"]["audio_url"].startswith("mock://tts/"))
        self.assertFalse(robot_message["payload"]["audio_url"].endswith(".mp3"))


if __name__ == "__main__":
    unittest.main()
