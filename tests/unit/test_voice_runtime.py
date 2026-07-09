"""Unit tests for the resident voice runtime text loop."""

from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


class CountingASRBackend:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio_clip: dict) -> dict:
        self.calls += 1
        return {
            "text": "小安你好",
            "language": "zh",
            "confidence": 0.9,
            "backend": "counting",
            "duration_ms": int(audio_clip.get("duration_ms") or 0),
        }


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

    async def test_process_text_can_disable_companion_fast_path(self) -> None:
        runtime = FakeRuntime(
            db_path=":memory:",
            robot_ws_url="ws://example.invalid/agent",
        )

        await voice_runtime.process_text(
            runtime,
            "我有点累",
            session_id="voice-test",
            disable_companion_fast_path=True,
        )

        event = runtime.brain.events[0]
        self.assertTrue(event["payload"]["disable_companion_fast_path"])

    def test_recording_status_preserves_previous_output(self) -> None:
        status = voice_runtime._recording_status(
            session_id="voice-test",
            wav_path=Path("runtime/test.wav"),
            sample_rate=16000,
            duration_seconds=6.0,
            previous_output={"text": "上一句", "reply_text": "上一条回复"},
        )

        self.assertEqual(status["event_type"], "voice.recording")
        self.assertEqual(status["previous_output"]["text"], "上一句")

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
        with tempfile.TemporaryDirectory() as temp_dir:
            latest_path = Path(temp_dir) / "latest_voice.json"

            count = await voice_runtime.run_text_loop(
                runtime_factory=FakeRuntime,
                input_stream=input_stream,
                output_stream=output_stream,
                error_stream=error_stream,
                db_path="test.db",
                gateway_url="ws://127.0.0.1:8765/agent",
                session_id="loop-test",
                prompt=False,
                latest_output_path=str(latest_path),
            )

            latest = json.loads(latest_path.read_text(encoding="utf-8"))

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
        self.assertEqual(latest["text"], "第二句")
        self.assertEqual(latest["display_text"], "display:第二句")
        self.assertIn("updated_at", latest)

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
            latest_path = Path(temp_dir) / "latest_voice.json"
            output = await voice_runtime.process_audio_file(
                runtime,
                str(audio_path),
                session_id="mic-test",
                asr_backend="fake",
                vad_backend="energy",
                trim_speech=False,
                latest_output_path=str(latest_path),
            )
            pending = json.loads(latest_path.read_text(encoding="utf-8"))

        self.assertEqual(output["event_type"], "asr.transcript")
        self.assertEqual(runtime.brain.events[0]["payload"]["source"], "local_mic")
        self.assertEqual(runtime.brain.events[0]["payload"]["session_id"], "mic-test")
        self.assertEqual(runtime.latest_replies[0]["source"], "voice_runtime.local_mic")
        self.assertEqual(pending["event_type"], "asr.transcript")
        self.assertEqual(pending["reason"], "openclaw_pending")
        self.assertEqual(pending["text"], "帮我查一下天气")

    async def test_process_audio_file_can_reuse_precreated_asr_backend(self) -> None:
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
            backend = CountingASRBackend()
            output = await voice_runtime.process_audio_file(
                runtime,
                str(audio_path),
                session_id="mic-test",
                asr_backend="sensevoice",
                asr_backend_instance=backend,
                vad_backend="energy",
                trim_speech=False,
            )

        self.assertEqual(output["text"], "小安你好")
        self.assertEqual(backend.calls, 1)

    def test_prewarm_asr_skips_non_sensevoice_backend(self) -> None:
        result = voice_runtime.prewarm_asr_model(asr_backend="fake")

        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "prewarm_only_required_for_sensevoice")

    def test_ensure_asr_wav_format_downsamples_48k_to_16k(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.wav"
            target = Path(temp_dir) / "target.wav"
            samples = [0, 8000, -8000] * 16000
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(struct.pack("<" + "h" * len(samples), *samples))

            result = voice_runtime._ensure_asr_wav_format(source, target, sample_rate=16000, channels=1)

            with wave.open(str(result), "rb") as wav:
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertLess(wav.getnframes(), len(samples))

    async def test_local_mic_main_forwards_fast_demo_decision_options(self) -> None:
        args = voice_runtime.parse_args(
            [
                "--source",
                "local_mic",
                "--once",
                "--decision-mode",
                "local_demo",
                "--local-demo-link",
                "fast3",
                "--local-demo-send-to-robot",
                "--local-demo-allow-motion",
                "--local-demo-reminders-path",
                "runtime/reminders.json",
            ]
        )

        with patch.object(voice_runtime, "run_local_mic_loop", new=AsyncMock(return_value=1)) as run_loop:
            result = await voice_runtime.main(args)

        self.assertEqual(result, 0)
        kwargs = run_loop.await_args.kwargs
        self.assertEqual(kwargs["decision_mode"], "local_demo")
        self.assertEqual(kwargs["local_demo_link"], "fast3")
        self.assertTrue(kwargs["local_demo_send_to_robot"])
        self.assertTrue(kwargs["local_demo_allow_motion"])
        self.assertEqual(kwargs["local_demo_reminders_path"], "runtime/reminders.json")


if __name__ == "__main__":
    unittest.main()
