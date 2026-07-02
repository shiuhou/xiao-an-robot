"""Unit tests for Demo 1 USB mic to Agent screen helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.demo.demo1_usb_mic_to_agent_screen import (
    append_log,
    build_state,
    choose_input_device,
    load_state,
    parse_arecord_devices,
    recording_sample_rate,
    write_transcript_text,
    write_state,
)


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


if __name__ == "__main__":
    unittest.main()
