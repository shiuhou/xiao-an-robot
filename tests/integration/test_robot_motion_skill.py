"""Integration tests for RobotMotionSkill over the local WebSocket MVP."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

try:
    import websockets
except ImportError:  # pragma: no cover - depends on local dev environment
    websockets = None

from agent.core.action_executor import ActionExecutor
from agent.core.gateway import RobotGateway
from agent.core.memory import XiaoAnMemoryStore
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall
from agent.skills.robot_motion import RobotMotionSkill

if websockets is not None:
    from base_station.ws_server import server as ws_server
else:  # pragma: no cover - import is skipped with the dependency
    ws_server = None


CARE_TEXT = "你已经工作很久了，休息一下吧。"


def build_message(msg_type: str, seq: int, payload: dict) -> str:
    return json.dumps({
        "type": msg_type,
        "ts": 1714538000000 + seq,
        "seq": seq,
        "payload": payload,
    }, ensure_ascii=False)


@unittest.skipIf(websockets is None, "websockets dependency is not installed")
class RobotMotionSkillIntegrationTest(unittest.IsolatedAsyncioTestCase):
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
                    "device_id": "skill-test-robot",
                    "firmware": "integration-test",
                    "battery": 92,
                },
            )),
            timeout=2,
        )
        welcome = await self.recv_json(self.robot)
        self.assertEqual(welcome["type"], "system.welcome")

        gateway = RobotGateway(url=f"ws://127.0.0.1:{self.port}/agent", timeout_sec=2)
        self.skill = RobotMotionSkill(gateway=gateway)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory_store = XiaoAnMemoryStore(
            db_path=str(Path(self.temp_dir.name) / "robot_motion_tool_runs.db"),
        )

    async def asyncTearDown(self) -> None:
        if hasattr(self, "memory_store"):
            self.memory_store.close()
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()
        if hasattr(self, "robot"):
            await self.robot.close()
        if hasattr(self, "server"):
            self.server.close()
            await self.server.wait_closed()
        ws_server.reset_state_for_tests()

    async def recv_json(self, websocket) -> dict:
        raw = await asyncio.wait_for(websocket.recv(), timeout=2)
        return json.loads(raw)

    async def test_show_expression(self) -> None:
        ack = await asyncio.wait_for(self.skill.show_expression("caring"), timeout=2)
        robot_message = await self.recv_json(self.robot)

        self.assertTrue(ack["payload"]["ok"])
        self.assertEqual(robot_message["type"], "display.expression")
        self.assertEqual(robot_message["payload"]["expression"], "caring")

    async def test_move_out_of_dock(self) -> None:
        ack = await asyncio.wait_for(self.skill.move_out_of_dock(), timeout=2)
        robot_message = await self.recv_json(self.robot)

        self.assertTrue(ack["payload"]["ok"])
        self.assertEqual(robot_message["type"], "motion.execute")
        self.assertEqual(robot_message["payload"]["action"], "move_out_of_dock")
        self.assertEqual(robot_message["payload"]["params"]["speed"], 0.56)
        self.assertEqual(robot_message["payload"]["params"]["distance_cm"], 10.0)
        self.assertEqual(robot_message["payload"]["timeout_ms"], 1200)

    async def test_say(self) -> None:
        ack = await asyncio.wait_for(self.skill.say(CARE_TEXT), timeout=2)
        robot_message = await self.recv_json(self.robot)

        self.assertTrue(ack["payload"]["ok"])
        self.assertEqual(robot_message["type"], "audio.play_tts")
        self.assertIn(CARE_TEXT, robot_message["payload"]["text_preview"])

    async def test_care_for_user_sequence(self) -> None:
        acks = await asyncio.wait_for(self.skill.care_for_user(CARE_TEXT), timeout=2)
        robot_messages = [await self.recv_json(self.robot) for _ in range(3)]

        self.assertEqual(len(acks), 3)
        self.assertTrue(all(ack["payload"]["ok"] for ack in acks))
        self.assertEqual([message["type"] for message in robot_messages], [
            "display.expression",
            "motion.execute",
            "audio.play_tts",
        ])

    async def test_xiaoan_robot_care_tool_call_forwards_commands_and_records_tool_run(self) -> None:
        executor = ActionExecutor(
            self.skill,
            memory_store=self.memory_store,
        )
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="xiaoan.robot.care",
                    arguments={"text": CARE_TEXT},
                ),
            ],
        )

        result = await asyncio.wait_for(
            executor.execute(decision, source_event_type="frontend.message"),
            timeout=5,
        )
        robot_messages = [await self.recv_json(self.robot) for _ in range(3)]
        tool_runs = self.memory_store.query_recent_tool_runs(tool_name="xiaoan.robot.care")

        self.assertEqual(result["skipped_actions"], [])
        self.assertEqual(result["executed_actions"][0]["name"], "xiaoan.robot.care")
        self.assertEqual([message["type"] for message in robot_messages], [
            "display.expression",
            "motion.execute",
            "audio.play_tts",
        ])
        self.assertEqual(robot_messages[0]["payload"]["expression"], "caring")
        self.assertEqual(robot_messages[1]["payload"]["action"], "move_out_of_dock")
        self.assertEqual(robot_messages[1]["payload"]["params"]["speed"], 0.56)
        self.assertEqual(robot_messages[1]["payload"]["params"]["distance_cm"], 10.0)
        self.assertEqual(robot_messages[1]["payload"]["timeout_ms"], 1200)
        self.assertIn(CARE_TEXT, robot_messages[2]["payload"]["text_preview"])
        self.assertEqual(len(tool_runs), 1)
        self.assertEqual(tool_runs[0]["status"], "success")
        self.assertEqual(tool_runs[0]["source_event_type"], "frontend.message")

    async def test_xiaoan_robot_care_tool_call_reports_offline_robot(self) -> None:
        await self.robot.close()
        ws_server.reset_state_for_tests()
        executor = ActionExecutor(
            self.skill,
            memory_store=self.memory_store,
        )
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="xiaoan.robot.care",
                    arguments={"text": CARE_TEXT},
                ),
            ],
        )

        result = await asyncio.wait_for(
            executor.execute(decision, source_event_type="frontend.message"),
            timeout=5,
        )
        tool_runs = self.memory_store.query_recent_tool_runs(tool_name="xiaoan.robot.care")

        self.assertEqual(result["executed_actions"], [])
        self.assertEqual(result["skipped_actions"][0]["reason"], "robot_action_failed")
        self.assertIn("No online robot connected", result["skipped_actions"][0]["result"]["error"])
        self.assertEqual(len(tool_runs), 1)
        self.assertEqual(tool_runs[0]["status"], "failed")
        self.assertIn("No online robot connected", tool_runs[0]["error"])


if __name__ == "__main__":
    unittest.main()
