"""Integration tests for EmotionMonitorSkill over the local WebSocket MVP."""

from __future__ import annotations

import asyncio
import json
import unittest

try:
    import websockets
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None

from agent.core.gateway import RobotGateway
from agent.skills.emotion_monitor import EmotionMonitorSkill

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
class EmotionMonitorSkillIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ws_server.reset_state_for_tests()
        self.server = await ws_server.start_server("127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.robot = await asyncio.wait_for(
            websockets.connect(f"ws://127.0.0.1:{self.port}/control"),
            timeout=2,
        )

        await asyncio.wait_for(
            self.robot.send(build_message(
                "device.hello",
                1,
                {
                    "device_id": "emotion-monitor-test-robot",
                    "firmware": "integration-test",
                    "battery": 91,
                },
            )),
            timeout=2,
        )
        welcome = await self.recv_json(self.robot)
        self.assertEqual(welcome["type"], "system.welcome")

        gateway = RobotGateway(url=f"ws://127.0.0.1:{self.port}/agent", timeout_sec=2)
        self.skill = EmotionMonitorSkill(gateway=gateway)

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

    async def test_high_fatigue_forwards_care_sequence(self) -> None:
        result = await asyncio.wait_for(
            self.skill.run({
                "emotion_tag": "neutral",
                "confidence": 0.9,
                "fatigue_score": 0.85,
            }),
            timeout=2,
        )
        robot_messages = [await self.recv_json(self.robot) for _ in range(3)]

        self.assertTrue(result["handled"])
        self.assertEqual(result["reason"], "fatigue")
        self.assertEqual([message["type"] for message in robot_messages], [
            "display.expression",
            "motion.execute",
            "audio.play_tts",
        ])


if __name__ == "__main__":
    unittest.main()
