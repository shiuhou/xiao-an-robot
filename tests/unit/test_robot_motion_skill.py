"""Unit tests for the local RobotMotionSkill wrapper."""

from __future__ import annotations

import unittest

from agent.skills.robot_motion import RobotMotionSkill


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    async def send_expression(self, expression: str, duration_ms: int = 3000, loop: bool = False) -> dict:
        self.calls.append(("expression", expression, duration_ms, loop))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "display.expression"}}

    async def send_motion(self, action: str, params: dict | None = None, timeout_ms: int = 5000) -> dict:
        self.calls.append(("motion", action, params or {}, timeout_ms))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "motion.execute"}}

    async def send_tts(self, text: str) -> dict:
        self.calls.append(("tts", text))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "audio.play_tts"}}


class RobotMotionSkillTest(unittest.IsolatedAsyncioTestCase):
    async def test_care_for_user_runs_expression_motion_and_tts(self) -> None:
        gateway = FakeGateway()
        skill = RobotMotionSkill(gateway=gateway)

        result = await skill.care_for_user("take a short break")

        self.assertEqual(len(result), 3)
        self.assertEqual(gateway.calls, [
            ("expression", "caring", 3000, False),
            ("motion", "move_out_of_dock", {"speed": 0.2, "distance_cm": 2.0}, 500),
            ("tts", "take a short break"),
        ])

    async def test_run_keeps_compatibility_entry_point(self) -> None:
        gateway = FakeGateway()
        skill = RobotMotionSkill(gateway=gateway)

        await skill.run("show_expression", {"expression": "happy", "duration_ms": 1000})
        await skill.run("move_out_of_dock")
        await skill.run("say", {"text": "hello"})

        self.assertEqual(gateway.calls, [
            ("expression", "happy", 1000, False),
            ("motion", "move_out_of_dock", {"speed": 0.2, "distance_cm": 2.0}, 500),
            ("tts", "hello"),
        ])

    async def test_return_to_dock_sends_protocol_action(self) -> None:
        gateway = FakeGateway()
        skill = RobotMotionSkill(gateway=gateway)

        await skill.return_to_dock()

        self.assertEqual(gateway.calls, [
            ("motion", "move_back_to_dock", {"speed": 0.2}, 500),
        ])

    async def test_run_accepts_legacy_return_to_dock_action(self) -> None:
        gateway = FakeGateway()
        skill = RobotMotionSkill(gateway=gateway)

        await skill.run("return_to_dock")

        self.assertEqual(gateway.calls, [
            ("motion", "move_back_to_dock", {"speed": 0.2}, 500),
        ])

    async def test_run_accepts_protocol_move_back_to_dock_action(self) -> None:
        gateway = FakeGateway()
        skill = RobotMotionSkill(gateway=gateway)

        await skill.run("move_back_to_dock")

        self.assertEqual(gateway.calls, [
            ("motion", "move_back_to_dock", {"speed": 0.2}, 500),
        ])

    async def test_motion_parameters_are_clamped_for_hardware_safety(self) -> None:
        gateway = FakeGateway()
        skill = RobotMotionSkill(gateway=gateway)

        await skill.move_out_of_dock(speed=5, distance_cm=99, timeout_ms=20000)
        await skill.return_to_dock(speed=5, timeout_ms=20000)

        self.assertEqual(gateway.calls, [
            ("motion", "move_out_of_dock", {"speed": 0.2, "distance_cm": 2.0}, 500),
            ("motion", "move_back_to_dock", {"speed": 0.2}, 500),
        ])


if __name__ == "__main__":
    unittest.main()
