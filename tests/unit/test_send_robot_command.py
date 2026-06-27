"""Unit tests for the local send_robot_command CLI payload builder."""

from __future__ import annotations

import argparse
import sys
import unittest
from unittest.mock import patch

from tools.send_robot_command import build_agent_command, parse_args


class SendRobotCommandTest(unittest.TestCase):
    def build_payload_from_argv(self, argv: list[str]) -> dict:
        with patch.object(sys, "argv", ["send_robot_command.py", *argv]):
            args = parse_args()
        return build_agent_command(args)["payload"]

    def test_expression_command_includes_duration_and_loop_defaults(self) -> None:
        message = build_agent_command(argparse.Namespace(
            command_name="expression",
            expression="caring",
            duration_ms=3000,
            loop=False,
            device_id=None,
        ))

        self.assertEqual(message["type"], "agent.command")
        self.assertEqual(message["payload"], {
            "command": "display.expression",
            "expression": "caring",
            "duration_ms": 3000,
            "loop": False,
        })

    def test_expression_positional_command_builds_phase_one_payload(self) -> None:
        payload = self.build_payload_from_argv(["expression", "caring"])

        self.assertEqual(payload["command"], "display.expression")
        self.assertEqual(payload["expression"], "caring")
        self.assertEqual(payload["duration_ms"], 3000)
        self.assertFalse(payload["loop"])

    def test_motion_positional_command_builds_phase_one_payload(self) -> None:
        payload = self.build_payload_from_argv(["motion", "move_out_of_dock"])

        self.assertEqual(payload, {
            "command": "motion.execute",
            "action": "move_out_of_dock",
        })

    def test_motion_command_raises_low_non_bench_speed_to_effective_minimum(self) -> None:
        payload = self.build_payload_from_argv([
            "motion",
            "move_out_of_dock",
            "--speed",
            "0.15",
            "--distance-cm",
            "1",
            "--timeout-ms",
            "250",
        ])

        self.assertEqual(payload, {
            "command": "motion.execute",
            "action": "move_out_of_dock",
            "params": {
                "speed": 0.52,
                "distance_cm": 1.0,
            },
            "timeout_ms": 250,
        })

    def test_motion_command_clamps_dangerous_parameters(self) -> None:
        payload = self.build_payload_from_argv([
            "motion",
            "move_out_of_dock",
            "--speed",
            "4",
            "--distance-cm",
            "99",
            "--timeout-ms",
            "9000",
        ])

        self.assertEqual(payload, {
            "command": "motion.execute",
            "action": "move_out_of_dock",
            "params": {
                "speed": 0.56,
                "distance_cm": 10.0,
            },
            "timeout_ms": 1200,
        })

    def test_motion_bench_mode_allows_longer_full_speed_without_distance(self) -> None:
        payload = self.build_payload_from_argv([
            "motion",
            "forward",
            "--bench",
            "--speed",
            "1.0",
            "--duration-ms",
            "5000",
            "--timeout-ms",
            "5000",
        ])

        self.assertEqual(payload, {
            "command": "motion.execute",
            "action": "move_out_of_dock",
            "bench": True,
            "params": {
                "speed": 1.0,
                "duration_ms": 5000,
            },
            "timeout_ms": 5000,
        })

    def test_motion_direction_aliases_map_to_protocol_actions(self) -> None:
        cases = {
            "forward": ("move_out_of_dock", {}),
            "back": ("move_back_to_dock", {}),
            "left": ("turn", {"angle_deg": -30.0}),
            "right": ("turn", {"angle_deg": 30.0}),
        }

        for alias, (action, extra_params) in cases.items():
            with self.subTest(alias=alias):
                payload = self.build_payload_from_argv([
                    "motion",
                    alias,
                    "--bench",
                    "--speed",
                    "0.4",
                    "--duration-ms",
                    "1200",
                    "--timeout-ms",
                    "1500",
                ])

                expected_params = {"speed": 0.4, "duration_ms": 1200, **extra_params}
                self.assertEqual(payload["action"], action)
                self.assertEqual(payload["params"], expected_params)
                self.assertEqual(payload["timeout_ms"], 1500)

    def test_local_sound_positional_command_defaults_to_safe_volume(self) -> None:
        payload = self.build_payload_from_argv(["local", "care_01"])

        self.assertEqual(payload, {
            "command": "audio.play_local",
            "sound": "care_01",
            "volume": 0.7,
        })

    def test_local_sound_positional_command_accepts_alarm_and_wake_chimes(self) -> None:
        for sound in ("alarm_01", "wake_01"):
            with self.subTest(sound=sound):
                payload = self.build_payload_from_argv(["local", sound])

                self.assertEqual(payload, {
                    "command": "audio.play_local",
                    "sound": sound,
                    "volume": 0.7,
                })

    def test_tts_command_builds_mock_tts_payload_from_text(self) -> None:
        payload = self.build_payload_from_argv(["tts", "--text", "hello xiao an"])

        self.assertEqual(payload, {
            "command": "audio.play_tts",
            "text": "hello xiao an",
        })


if __name__ == "__main__":
    unittest.main()
