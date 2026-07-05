"""Unit tests for the resident voice runtime text loop."""

from __future__ import annotations

import io
import json
import unittest

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
        FakeRuntime.instances.append(self)

    def close(self) -> None:
        self.closed = True


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
        args = voice_runtime.parse_args(["--source", "local_mic"])

        with self.assertRaisesRegex(NotImplementedError, "reserved"):
            await voice_runtime.main(args)


if __name__ == "__main__":
    unittest.main()
