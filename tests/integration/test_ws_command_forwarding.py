"""Integration tests for Agent -> BaseStation -> Robot command forwarding."""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

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
            "speed": 0.56,
            "distance_cm": 10.0,
        })
        self.assertEqual(robot_message["payload"]["timeout_ms"], 1200)

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
            "speed": 0.56,
            "distance_cm": 10.0,
        })
        self.assertEqual(robot_message["payload"]["timeout_ms"], 1200)

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

    async def test_audio_play_tts_command_defaults_to_metadata_only(self) -> None:
        text = "hello xiao an"

        original_synthesizer = ws_server.synthesize_tts_pcm_stream
        ws_server.synthesize_tts_pcm_stream = lambda requested_text: ws_server.TtsPcmStream(
            audio_id="tts-test-001",
            text_preview=requested_text,
            pcm=b"\x01\x02",
            sample_rate=16000,
            channels=1,
        )
        try:
            robot_message = await self.send_agent_command_and_assert_forwarded(
                {
                    "command": "audio.play_tts",
                    "text": text,
                },
                "audio.play_tts",
            )
        finally:
            ws_server.synthesize_tts_pcm_stream = original_synthesizer

        self.assertEqual(robot_message["payload"]["text_preview"], text)
        self.assertNotIn("audio_format", robot_message["payload"])
        self.assertNotIn("sample_rate", robot_message["payload"])
        self.assertNotIn("channels", robot_message["payload"])
        self.assertTrue(robot_message["payload"]["audio_url"].startswith("mock://tts/"))
        self.assertFalse(robot_message["payload"]["audio_url"].startswith("stream://control/"))
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.robot.recv(), timeout=0.05)

    async def test_audio_play_tts_command_streams_pcm_after_metadata(self) -> None:
        text = "hello xiao an"

        original_synthesizer = ws_server.synthesize_tts_pcm_stream
        ws_server.synthesize_tts_pcm_stream = lambda requested_text: ws_server.TtsPcmStream(
            audio_id="tts-test-001",
            text_preview=requested_text,
            pcm=b"\x01\x02\x03\x04",
            sample_rate=16000,
            channels=1,
        )
        try:
            with mock.patch.dict(
                "os.environ",
                {ws_server.CONTROL_TTS_STREAM_ENV: "1"},
                clear=False,
            ):
                await asyncio.wait_for(
                    self.agent.send(json.dumps({
                        "type": "agent.command",
                        "payload": {
                            "command": "audio.play_tts",
                            "text": text,
                        },
                    }, ensure_ascii=False)),
                    timeout=2,
                )

                robot_message = await self.recv_json(self.robot)
                self.assertEqual(robot_message["type"], "audio.play_tts")

                pcm_chunk = await asyncio.wait_for(self.robot.recv(), timeout=2)
                self.assertEqual(pcm_chunk, b"\x01\x02\x03\x04")

                stream_end = json.loads(await asyncio.wait_for(self.robot.recv(), timeout=2))
                self.assertEqual(stream_end["type"], "audio.stream_end")
                self.assertEqual(stream_end["payload"]["audio_id"], "tts-test-001")

                ack = await self.recv_json(self.agent)
                self.assertEqual(ack["type"], "agent.ack")
                self.assertTrue(ack["payload"]["ok"])
                self.assertEqual(ack["payload"]["device_id"], "test-robot-001")
                self.assertEqual(ack["payload"]["forwarded_type"], "audio.play_tts")
        finally:
            ws_server.synthesize_tts_pcm_stream = original_synthesizer

        self.assertEqual(robot_message["payload"]["text_preview"], text)
        self.assertEqual(robot_message["payload"]["audio_id"], "tts-test-001")
        self.assertEqual(robot_message["payload"]["audio_url"], "stream://control/tts-test-001")
        self.assertEqual(robot_message["payload"]["audio_format"], "pcm_s16le")
        self.assertEqual(robot_message["payload"]["sample_rate"], 16000)
        self.assertEqual(robot_message["payload"]["channels"], 1)


if __name__ == "__main__":
    unittest.main()
