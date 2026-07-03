"""Unit tests for Demo 1 USB mic to Agent screen helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.demo.demo1_usb_mic_to_agent_screen import (
    append_log,
    build_openclaw_asr_event,
    build_openclaw_context,
    build_rule_action_plan,
    build_state,
    choose_input_device,
    detect_expression_request,
    load_state,
    normalize_motion_for_gateway,
    parse_arecord_devices,
    post_motion_delay_seconds,
    recording_sample_rate,
    validate_openclaw_decision,
    validate_action_plan,
    write_transcript_text,
    write_state,
)
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawToolCall


class Demo1UsbMicToAgentScreenTest(unittest.TestCase):
    def test_write_state_preserves_mock_source_and_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "demo1_transcript.json"
            state = build_state(
                status="done",
                transcript="帮我记一下，今晚八点修改报告第三章",
                source="mock",
                audio_device="USB Microphone",
                asr_backend="mock",
            )

            write_state(state_path, state)
            loaded = load_state(state_path)

        self.assertEqual(loaded["status"], "done")
        self.assertEqual(loaded["source"], "mock")
        self.assertEqual(loaded["transcript"], "帮我记一下，今晚八点修改报告第三章")
        self.assertEqual(loaded["audio_device"], "USB Microphone")

    def test_append_log_writes_jsonl_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "demo1_transcript.log.jsonl"
            state = build_state(status="error", source="asr", error="ASR backend unavailable")

            append_log(log_path, state)
            line = log_path.read_text(encoding="utf-8").strip()

        self.assertEqual(json.loads(line)["error"], "ASR backend unavailable")

    def test_choose_input_device_prefers_usb_mic(self) -> None:
        devices = [
            {"index": 0, "name": "Built-in Audio Analog Stereo", "max_input_channels": 2},
            {"index": 2, "name": "USB PnP Microphone", "max_input_channels": 1},
        ]

        selected = choose_input_device(devices)

        self.assertEqual(selected["index"], 2)

    def test_choose_input_device_allows_index_or_name(self) -> None:
        devices = [
            {"index": 0, "name": "Built-in Mic", "max_input_channels": 2},
            {"index": 3, "name": "Conference USB Mic", "max_input_channels": 1},
        ]

        self.assertEqual(choose_input_device(devices, "3")["name"], "Conference USB Mic")
        self.assertEqual(choose_input_device(devices, "conference")["index"], 3)

    def test_parse_arecord_devices_supports_usb_hw_id(self) -> None:
        output = """
card 0: PCH [HDA Intel PCH], device 0: ALC897 Analog [ALC897 Analog]
card 1: UACDemoV10 [UACDemoV1.0], device 0: USB Audio [USB Audio]
"""

        devices = parse_arecord_devices(output)

        self.assertEqual(devices[1]["backend"], "arecord")
        self.assertEqual(devices[1]["index"], "hw:1,0")
        self.assertEqual(devices[1]["device_id"], "plughw:1,0")
        self.assertEqual(devices[1]["hardware_id"], "hw:1,0")
        self.assertEqual(choose_input_device(devices, "hw:1,0")["name"], "UACDemoV1.0 USB Audio")
        self.assertEqual(choose_input_device(devices, "1")["device_id"], "plughw:1,0")

    def test_choose_input_device_prefers_arecord_usb_when_available(self) -> None:
        devices = [
            {
                "backend": "pyaudio",
                "index": 5,
                "device_id": "5",
                "name": "UACDemoV1.0: USB Audio (hw:1,0)",
                "max_input_channels": 1,
                "default_sample_rate": 48000.0,
            },
            {
                "backend": "arecord",
                "index": "hw:1,0",
                "device_id": "plughw:1,0",
                "hardware_id": "hw:1,0",
                "card": 1,
                "device": 0,
                "name": "UACDemoV1.0 USB Audio",
                "max_input_channels": 1,
                "default_sample_rate": 16000.0,
            },
        ]

        self.assertEqual(choose_input_device(devices)["backend"], "arecord")
        self.assertEqual(choose_input_device(devices, "5")["backend"], "pyaudio")
        self.assertEqual(choose_input_device(devices, "hw:1,0")["backend"], "arecord")

    def test_recording_sample_rate_uses_pyaudio_default_rate(self) -> None:
        device = {"backend": "pyaudio", "default_sample_rate": 48000.0}

        self.assertEqual(recording_sample_rate(device, 16000), 48000)
        self.assertEqual(recording_sample_rate({"backend": "arecord"}, 16000), 16000)

    def test_write_transcript_text_writes_plain_text_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            text_path = Path(temp_dir) / "demo1_transcript.txt"

            write_transcript_text(text_path, "  麦克风识别结果  ")

            self.assertEqual(text_path.read_text(encoding="utf-8"), "麦克风识别结果\n")

    def test_build_openclaw_context_wraps_asr_transcript(self) -> None:
        context = build_openclaw_context(
            transcript="我有点累",
            source="asr",
            audio_device="UACDemoV1.0 USB Audio",
            audio_path="runtime/demo1_audio/sample.wav",
            asr_output={"text": "我有点累"},
        )

        self.assertEqual(context["schema_version"], "demo1.openclaw_context.v1")
        self.assertEqual(context["event_type"], "asr.transcript")
        self.assertEqual(context["transcript"], "我有点累")
        self.assertEqual(context["source"], "base_station_mic")
        self.assertEqual(context["transcript_source"], "asr")
        self.assertIn("robot_state", context)
        self.assertIn("vision_context", context)
        self.assertIn("last_action", context)
        self.assertEqual(context["demo_intent"], "care_companion")
        self.assertIn("display.expression", context["allowed_actions"])
        self.assertIn("care_01", context["allowed_actions"]["audio.play_local"]["audio_id"])
        self.assertIn("surprised", context["allowed_actions"]["display.expression"]["expression"])
        self.assertEqual(
            context["openclaw_tool_contract"]["decision_owner"],
            "openclaw_xiaoan_runtime",
        )

    def test_build_openclaw_asr_event_uses_base_station_mic_source(self) -> None:
        context = build_openclaw_context(transcript="小安，我有点累", source="asr")

        event = build_openclaw_asr_event(
            transcript="小安，我有点累",
            context=context,
            session_id="demo1-test",
        )

        self.assertEqual(event.type, "asr.transcript")
        self.assertEqual(event.source, "base_station_mic")
        self.assertEqual(event.session_id, "demo1-test")
        self.assertEqual(event.context["transcript"], "小安，我有点累")

    def test_validate_openclaw_decision_rejects_unsupported_expression(self) -> None:
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name="xiaoan.robot.expression",
                    arguments={"expression": "angry"},
                )
            ],
        )

        validation = validate_openclaw_decision(decision)

        self.assertFalse(validation["ok"])
        self.assertIn(
            "tool_calls[0].arguments.expression not allowed: angry",
            validation["errors"],
        )

    def test_build_rule_action_plan_for_fatigue_text(self) -> None:
        plan = build_rule_action_plan("小安，我有点累")

        self.assertEqual(plan["schema_version"], "demo1.action_plan.v1")
        self.assertTrue(plan["handled"])
        self.assertEqual(plan["route"], "demo1_rule_care")
        self.assertTrue(plan["validation"]["ok"])
        self.assertIn("allowed_actions", plan)
        self.assertEqual(
            [action["name"] for action in plan["actions"]],
            [
                "display.expression",
                "motion.execute",
                "motion.execute",
                "audio.play_local",
            ],
        )
        self.assertEqual(plan["actions"][2]["arguments"]["action"], "left")
        self.assertEqual(plan["actions"][-1]["arguments"]["sound"], "care_01")

    def test_build_rule_action_plan_for_expression_request(self) -> None:
        plan = build_rule_action_plan("给我换一个开心的表情包")

        self.assertTrue(plan["handled"])
        self.assertEqual(plan["route"], "demo1_rule_expression")
        self.assertEqual(plan["reason"], "happy_expression_keyword")
        self.assertEqual(plan["actions"][0]["name"], "display.expression")
        self.assertEqual(plan["actions"][0]["arguments"]["expression"], "happy")

    def test_build_rule_action_plan_maps_unsupported_angry_to_surprised(self) -> None:
        plan = build_rule_action_plan("给我换一个愤怒的表情包怒的情包")

        self.assertTrue(plan["handled"])
        self.assertEqual(plan["route"], "demo1_rule_expression")
        self.assertEqual(plan["reason"], "unsupported_angry_expression_fallback")
        self.assertEqual(plan["actions"][0]["arguments"]["expression"], "surprised")
        self.assertTrue(plan["validation"]["ok"])

    def test_detect_expression_request_requires_expression_keyword(self) -> None:
        self.assertIsNone(detect_expression_request("我有点生气"))
        self.assertEqual(
            detect_expression_request("切换到惊讶表情"),
            ("surprised", "surprised_expression_keyword"),
        )

    def test_build_rule_action_plan_ignores_non_demo_text(self) -> None:
        plan = build_rule_action_plan("今天天气怎么样")

        self.assertFalse(plan["handled"])
        self.assertEqual(plan["route"], "demo1_rule_noop")
        self.assertEqual(plan["actions"], [])
        self.assertTrue(plan["validation"]["ok"])

    def test_validate_action_plan_rejects_actions_outside_allowed_set(self) -> None:
        plan = build_rule_action_plan("小安，我有点累")
        plan["actions"].append({"name": "robot.dance", "arguments": {"style": "free"}})

        validation = validate_action_plan(plan)

        self.assertFalse(validation["ok"])
        self.assertIn("actions[4].name not allowed: robot.dance", validation["errors"])

    def test_validate_action_plan_rejects_invalid_motion_argument(self) -> None:
        plan = build_rule_action_plan("小安，我有点累")
        plan["actions"][1]["arguments"]["action"] = "turn"

        validation = validate_action_plan(plan)

        self.assertFalse(validation["ok"])
        self.assertIn("actions[1].arguments.action not allowed: turn", validation["errors"])

    def test_normalize_motion_for_gateway_maps_allowed_direction_to_protocol_turn(self) -> None:
        action, params = normalize_motion_for_gateway(
            {"action": "left", "params": {"speed": 0.52, "angle_deg": 20}}
        )

        self.assertEqual(action, "turn")
        self.assertEqual(params["angle_deg"], -20.0)

    def test_post_motion_delay_seconds_uses_timeout_with_bounds(self) -> None:
        self.assertAlmostEqual(post_motion_delay_seconds({"timeout_ms": 700}), 0.85)
        self.assertEqual(post_motion_delay_seconds({"timeout_ms": 5000}), 3.0)
        self.assertAlmostEqual(post_motion_delay_seconds({"timeout_ms": "bad"}), 1.35)


if __name__ == "__main__":
    unittest.main()
