"""Unit tests for the resident voice runtime text loop."""

from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from base_station.monitor import voice_runtime


class FakeBrain:
    def __init__(self) -> None:
        self.events = []

    async def handle_event(self, event: dict) -> dict:
        self.events.append(event)
        text = event["payload"]["text"]
        return {
            "handled": True,
            "route": "link_1_openclaw",
            "reason": "openclaw_decision",
            "openclaw_result": {
                "handled": True,
                "display_text": f"display:{text}",
                "spoken_text": f"spoken:{text}",
                "executed_actions": [
                    {
                        "name": "robot.say",
                        "arguments": {"text": f"spoken:{text}"},
                    },
                ],
                "skipped_actions": [],
            },
        }


class FakeRuntime:
    instances = []

    def __init__(self, db_path: str, robot_ws_url: str, verbose: bool = False) -> None:
        self.db_path = db_path
        self.robot_ws_url = robot_ws_url
        self.verbose = verbose
        self.brain = FakeBrain()
        self.closed = False
        self.latest_replies = []
        FakeRuntime.instances.append(self)

    def close(self) -> None:
        self.closed = True

    def _set_latest_reply(self, **kwargs) -> dict:
        self.latest_replies.append(kwargs)
        return kwargs


class NativeReplyBrain:
    def __init__(self) -> None:
        self.events = []

    async def handle_event(self, event: dict) -> dict:
        self.events.append(event)
        return {
            "handled": True,
            "route": "link_1_openclaw",
            "reason": "openclaw_decision",
            "display_text": "已把任务写入 TASKS.md，并更新今日重点。",
            "reply_text": "我已经更新任务清单。",
            "executed_actions": [],
            "skipped_actions": [],
        }


class NativeReplyRuntime(FakeRuntime):
    def __init__(self, db_path: str, robot_ws_url: str, verbose: bool = False) -> None:
        super().__init__(db_path=db_path, robot_ws_url=robot_ws_url, verbose=verbose)
        self.brain = NativeReplyBrain()


class KeyboardInterruptStream:
    def readline(self) -> str:
        raise KeyboardInterrupt


class VoiceRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeRuntime.instances = []

    async def test_process_text_sends_asr_transcript_event_to_existing_runtime(self) -> None:
        runtime = FakeRuntime(
            db_path=":memory:",
            robot_ws_url="ws://example.invalid/agent",
        )

        output = await voice_runtime.process_text(
            runtime,
            "  帮我查一下天气  ",
            session_id="voice-test",
        )

        self.assertEqual(len(runtime.brain.events), 1)
        event = runtime.brain.events[0]
        self.assertEqual(event["type"], "asr.transcript")
        self.assertEqual(event["payload"]["source"], "text_loop")
        self.assertEqual(event["payload"]["session_id"], "voice-test")
        self.assertEqual(event["payload"]["text"], "帮我查一下天气")
        self.assertEqual(output["route"], "link_1_openclaw")
        self.assertEqual(output["display_text"], "display:帮我查一下天气")
        self.assertEqual(output["spoken_text"], "spoken:帮我查一下天气")
        self.assertEqual(output["executed_actions"][0]["name"], "robot.say")
        self.assertEqual(runtime.latest_replies[0]["notification_type"], "asr.transcript")
        self.assertEqual(runtime.latest_replies[0]["display_text"], "display:帮我查一下天气")
        self.assertEqual(runtime.latest_replies[0]["source"], "voice_runtime.text_loop")

    async def test_process_text_publishes_native_openclaw_reply_to_dashboard(self) -> None:
        runtime = NativeReplyRuntime(
            db_path=":memory:",
            robot_ws_url="ws://example.invalid/agent",
        )

        output = await voice_runtime.process_text(
            runtime,
            "把今天任务整理一下",
            session_id="native-work",
        )

        self.assertEqual(output["display_text"], "已把任务写入 TASKS.md，并更新今日重点。")
        self.assertEqual(len(runtime.latest_replies), 1)
        latest = runtime.latest_replies[0]
        self.assertEqual(latest["display_text"], "已把任务写入 TASKS.md，并更新今日重点。")
        self.assertEqual(latest["reply_text"], "我已经更新任务清单。")
        self.assertEqual(latest["metadata"]["route"], "link_1_openclaw")
        self.assertEqual(latest["session_id"], "native-work")

    async def test_text_loop_reuses_one_runtime_for_multiple_lines(self) -> None:
        input_stream = io.StringIO("\n第一句\n第二句\n")
        output_stream = io.StringIO()
        error_stream = io.StringIO()

        count = await voice_runtime.run_text_loop(
            runtime_factory=FakeRuntime,
            input_stream=input_stream,
            output_stream=output_stream,
            error_stream=error_stream,
            db_path="test.db",
            gateway_url="ws://127.0.0.1:8765/agent",
            session_id="loop-test",
            prompt=False,
        )

        self.assertEqual(count, 2)
        self.assertEqual(len(FakeRuntime.instances), 1)
        runtime = FakeRuntime.instances[0]
        self.assertTrue(runtime.closed)
        self.assertEqual([event["payload"]["text"] for event in runtime.brain.events], ["第一句", "第二句"])

        lines = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["text"], "第一句")
        self.assertEqual(lines[0]["display_text"], "display:第一句")
        self.assertEqual(lines[0]["spoken_text"], "spoken:第一句")
        self.assertEqual(lines[0]["executed_actions"][0]["name"], "robot.say")
        self.assertEqual(error_stream.getvalue(), "")

    async def test_text_loop_ctrl_c_exits_and_closes_runtime(self) -> None:
        output_stream = io.StringIO()
        error_stream = io.StringIO()

        count = await voice_runtime.run_text_loop(
            runtime_factory=FakeRuntime,
            input_stream=KeyboardInterruptStream(),
            output_stream=output_stream,
            error_stream=error_stream,
            prompt=False,
        )

        self.assertEqual(count, 0)
        self.assertEqual(len(FakeRuntime.instances), 1)
        self.assertTrue(FakeRuntime.instances[0].closed)
        self.assertIn("voice_runtime stopped", error_stream.getvalue())

    async def test_reserved_sources_are_rejected_without_starting_loop(self) -> None:
        args = voice_runtime.parse_args(["--source", "audio_file_loop"])

        with self.assertRaisesRegex(NotImplementedError, "reserved"):
            await voice_runtime.main(args)

    async def test_process_audio_file_uses_vad_asr_and_publishes_latest_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "speech.wav"
            samples = [4000] * 16000
            with wave.open(str(audio_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(struct.pack("<" + "h" * len(samples), *samples))

            runtime = FakeRuntime(
                db_path=":memory:",
                robot_ws_url="ws://example.invalid/agent",
            )
            output = await voice_runtime.process_audio_file(
                runtime,
                str(audio_path),
                session_id="mic-test",
                asr_backend="fake",
                vad_backend="energy",
                trim_speech=False,
            )

        self.assertEqual(output["event_type"], "asr.transcript")
        self.assertEqual(runtime.brain.events[0]["payload"]["source"], "local_mic")
        self.assertEqual(runtime.brain.events[0]["payload"]["session_id"], "mic-test")
        self.assertEqual(runtime.latest_replies[0]["source"], "voice_runtime.local_mic")


if __name__ == "__main__":
    unittest.main()
