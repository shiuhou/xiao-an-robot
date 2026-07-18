"""Unit tests for the resident voice runtime text loop."""

from __future__ import annotations

import io
import json
import os
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

from base_station.monitor import voice_runtime
from agent.core.work_mode import WorkModeStore


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
            "openclaw_raw": {
                "capture": {
                    "status": "captured",
                    "kind": "task",
                    "title": text,
                },
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


class PunctuationASRBackend:
    def transcribe(self, audio_clip: dict) -> dict:
        return {
            "text": "。",
            "language": "zh",
            "confidence": 0.1,
            "backend": "punctuation",
            "duration_ms": int(audio_clip.get("duration_ms") or 0),
        }


class FakePersistentRecorder:
    instances = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.recorded = []
        self.discarded = []
        self.read_windows = []
        self.closed = False
        FakePersistentRecorder.instances.append(self)

    def __enter__(self):
        return self

    def record_window(self, output_path: str | Path, duration_seconds: float) -> Path:
        self.recorded.append((str(output_path), duration_seconds))
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            samples = [4000] * max(1, int(16000 * duration_seconds))
            wav.writeframes(struct.pack("<" + "h" * len(samples), *samples))
        return path

    def discard_window(self, duration_seconds: float) -> int:
        self.discarded.append(duration_seconds)
        return int(16000 * duration_seconds * 2)

    def read_window(self, duration_seconds: float) -> bytes:
        self.read_windows.append(duration_seconds)
        frame_count = max(1, int(16000 * duration_seconds))
        return struct.pack("<" + "h" * frame_count, *([4000] * frame_count))

    def close(self) -> None:
        self.closed = True


class ToggleOffRecorder(FakePersistentRecorder):
    state_path: Path | None = None
    stop_after_reads = 3

    def read_window(self, duration_seconds: float) -> bytes:
        data = super().read_window(duration_seconds)
        if len(self.read_windows) >= self.stop_after_reads and self.state_path is not None:
            WorkModeStore(self.state_path, cooldown_seconds=0).update_controls(
                system_enabled=True,
                mic_recognition_enabled=False,
                camera_capture_enabled=True,
            )
        return data


class VoiceRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeRuntime.instances = []
        FakePersistentRecorder.instances = []
        ToggleOffRecorder.state_path = None
        ToggleOffRecorder.stop_after_reads = 3

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
        self.assertEqual(output["openclaw_raw"]["capture"]["title"], "帮我查一下天气")
        self.assertEqual(output["executed_actions"][0]["name"], "robot.say")
        self.assertEqual(runtime.latest_replies[0]["notification_type"], "asr.transcript")
        self.assertEqual(runtime.latest_replies[0]["display_text"], "display:帮我查一下天气")
        self.assertEqual(
            runtime.latest_replies[0]["execution_result"]["openclaw_raw"]["capture"]["kind"],
            "task",
        )
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

    def test_muted_status_preserves_meaningful_previous_output_without_nesting(self) -> None:
        first = {
            "event_type": "asr.transcript",
            "text": "小安在吗",
            "reply_text": "我在。",
        }
        muted_once = voice_runtime._muted_status("voice-test", first)
        muted_twice = voice_runtime._muted_status("voice-test", muted_once)

        self.assertEqual(muted_twice["event_type"], "voice.muted")
        self.assertEqual(muted_twice["previous_output"], first)
        self.assertNotEqual(muted_twice["previous_output"].get("event_type"), "voice.muted")

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

    def test_openclaw_reminder_fallback_appends_local_reminder_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reminders_path = Path(temp_dir) / "reminders.json"
            output = {
                "display_text": "好呀，一分钟后提醒你喝水。",
                "reply_text": "好呀，一分钟后提醒你喝水。",
                "openclaw_raw": {
                    "capture": {
                        "status": "captured",
                        "kind": "reminder",
                        "source_of_truth": "base_station_local_reminder_fallback",
                        "title": "喝水",
                        "due_at": "2026-07-17T22:00:00+08:00",
                        "time_text": "一分钟后",
                        "metadata": {"fallback_reason": "openclaw_missing_cron_tool"},
                    },
                },
            }

            record = voice_runtime._maybe_schedule_openclaw_reminder_fallback(
                output,
                "小安，一分钟后提醒我喝水。",
                reminders_path=str(reminders_path),
                send_to_robot=True,
                allow_motion=False,
                gateway_url="ws://127.0.0.1:8765/agent",
            )
            saved = json.loads(reminders_path.read_text(encoding="utf-8"))

        self.assertIsNotNone(record)
        self.assertEqual(saved["schema_version"], "xiaoan.fast_demo_reminders.v1")
        self.assertEqual(len(saved["items"]), 1)
        item = saved["items"][0]
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["source"], "openclaw_reminder_fallback")
        self.assertEqual(item["due_at"], "2026-07-17T22:00:00+08:00")
        self.assertEqual(item["reminder"]["title"], "喝水")
        self.assertTrue(item["send_to_robot"])
        self.assertFalse(item["allow_motion"])
        self.assertEqual(output["scheduled_reminder"]["id"], item["id"])
        self.assertEqual(output["local_reminder_fallback"]["reason"], "openclaw_missing_cron_tool")

    def test_openclaw_reminder_fallback_without_explicit_time_is_not_scheduled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reminders_path = Path(temp_dir) / "reminders.json"
            output = {
                "display_text": "需要具体提醒时间才能创建提醒。",
                "openclaw_raw": {
                    "capture": {
                        "status": "captured",
                        "kind": "reminder",
                        "source_of_truth": "base_station_local_reminder_fallback",
                        "title": "喝水",
                        "metadata": {"fallback_reason": "openclaw_missing_cron_tool"},
                    },
                },
            }

            record = voice_runtime._maybe_schedule_openclaw_reminder_fallback(
                output,
                "小安提醒我喝水。",
                reminders_path=str(reminders_path),
                send_to_robot=True,
                allow_motion=False,
                gateway_url="ws://127.0.0.1:8765/agent",
            )

            self.assertIsNone(record)
            self.assertFalse(reminders_path.exists())
            self.assertNotIn("scheduled_reminder", output)

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

    async def test_process_audio_file_does_not_route_punctuation_only_transcript(self) -> None:
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
            state_path = Path(temp_dir) / "work_mode_state.json"
            store = WorkModeStore(state_path)
            store.acquire_episode(chain="link1", source="asr", text="旧 active")
            with patch.dict(os.environ, {"XIAOAN_WORK_MODE_STATE_PATH": str(state_path)}):
                output = await voice_runtime.process_audio_file(
                    runtime,
                    str(audio_path),
                    session_id="mic-test",
                    asr_backend="sensevoice",
                    asr_backend_instance=PunctuationASRBackend(),
                    vad_backend="energy",
                    trim_speech=False,
                    latest_output_path=str(latest_path),
                )
            state = store.snapshot()

        self.assertEqual(output["event_type"], "asr.empty_transcript")
        self.assertEqual(output["reason"], "asr_nonlexical_transcript")
        self.assertEqual(output["text"], "。")
        self.assertEqual(runtime.brain.events, [])
        self.assertFalse(latest_path.exists())
        self.assertIsNone(state["active_run_id"])
        self.assertEqual(state["last_episode"]["status"], "ignored")
        self.assertEqual(state["last_episode"]["result"]["reason"], "asr_nonlexical_transcript")

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

    async def test_local_mic_loop_keeps_recorder_open_and_discards_when_recognition_muted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "work_mode.json"
            WorkModeStore(state_path, cooldown_seconds=0).update_controls(
                system_enabled=True,
                mic_recognition_enabled=False,
                camera_capture_enabled=True,
            )
            old_env = os.environ.get("XIAOAN_WORK_MODE_STATE_PATH")
            os.environ["XIAOAN_WORK_MODE_STATE_PATH"] = str(state_path)
            try:
                with patch.object(voice_runtime, "PersistentWavRecorder", FakePersistentRecorder), patch.object(
                    voice_runtime,
                    "list_input_devices",
                    return_value=[{
                        "backend": "pyaudio",
                        "index": 0,
                        "device_id": "0",
                        "name": "unit mic",
                        "max_input_channels": 1,
                        "default_sample_rate": 16000,
                    }],
                ), patch.object(voice_runtime, "process_audio_file", new=AsyncMock()) as process_audio:
                    count = await voice_runtime.run_local_mic_loop(
                        runtime_factory=FakeRuntime,
                        output_stream=io.StringIO(),
                        error_stream=io.StringIO(),
                        db_path=":memory:",
                        once=True,
                        duration_seconds=1.0,
                        asr_backend="fake",
                        output_dir=str(Path(temp_dir) / "audio"),
                        work_mode_gated=True,
                    )
            finally:
                if old_env is None:
                    os.environ.pop("XIAOAN_WORK_MODE_STATE_PATH", None)
                else:
                    os.environ["XIAOAN_WORK_MODE_STATE_PATH"] = old_env

        self.assertEqual(count, 0)
        self.assertEqual(len(FakePersistentRecorder.instances), 1)
        self.assertEqual(FakePersistentRecorder.instances[0].discarded, [1.0])
        self.assertEqual(FakePersistentRecorder.instances[0].recorded, [])
        self.assertTrue(FakePersistentRecorder.instances[0].closed)
        self.assertFalse(process_audio.called)

    async def test_local_mic_loop_without_work_mode_gate_ignores_muted_work_mode_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "work_mode.json"
            WorkModeStore(state_path, cooldown_seconds=0).update_controls(
                system_enabled=True,
                mic_recognition_enabled=False,
                camera_capture_enabled=True,
            )
            old_env = os.environ.get("XIAOAN_WORK_MODE_STATE_PATH")
            os.environ["XIAOAN_WORK_MODE_STATE_PATH"] = str(state_path)
            output = {
                "event_type": "asr.transcript",
                "handled": True,
                "text": "小安能听到我吗",
            }
            try:
                with patch.object(voice_runtime, "PersistentWavRecorder", FakePersistentRecorder), patch.object(
                    voice_runtime,
                    "list_input_devices",
                    return_value=[{
                        "backend": "pyaudio",
                        "index": 0,
                        "device_id": "0",
                        "name": "unit mic",
                        "max_input_channels": 1,
                        "default_sample_rate": 16000,
                    }],
                ), patch.object(voice_runtime, "create_asr_backend", return_value=CountingASRBackend()), patch.object(
                    voice_runtime,
                    "process_audio_file",
                    new=AsyncMock(return_value=output),
                ) as process_audio:
                    count = await voice_runtime.run_local_mic_loop(
                        runtime_factory=FakeRuntime,
                        output_stream=io.StringIO(),
                        error_stream=io.StringIO(),
                        db_path=":memory:",
                        once=True,
                        duration_seconds=1.0,
                        asr_backend="fake",
                        output_dir=str(Path(temp_dir) / "audio"),
                    )
            finally:
                if old_env is None:
                    os.environ.pop("XIAOAN_WORK_MODE_STATE_PATH", None)
                else:
                    os.environ["XIAOAN_WORK_MODE_STATE_PATH"] = old_env

        self.assertEqual(count, 1)
        self.assertEqual(FakePersistentRecorder.instances[0].discarded, [])
        self.assertEqual(len(FakePersistentRecorder.instances[0].recorded), 1)
        self.assertTrue(process_audio.called)

    async def test_local_mic_loop_discards_short_window_after_robot_tts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            latest_output = Path(temp_dir) / "latest.json"
            first_output = {
                "event_type": "asr.transcript",
                "handled": True,
                "text": "小安你好",
                "route": "link_1_openclaw",
                "reason": "openclaw_decision",
                "tts_text": "你好，我在。",
                "executed_actions": [
                    {
                        "name": "robot.say",
                        "source": "reply_text",
                        "arguments": {"text": "你好，我在。"},
                    }
                ],
            }
            with patch.object(voice_runtime, "PersistentWavRecorder", FakePersistentRecorder), patch.object(
                voice_runtime,
                "list_input_devices",
                return_value=[{
                    "backend": "pyaudio",
                    "index": 0,
                    "device_id": "0",
                    "name": "unit mic",
                    "max_input_channels": 1,
                    "default_sample_rate": 16000,
                }],
            ), patch.object(voice_runtime, "create_asr_backend", return_value=CountingASRBackend()), patch.object(
                voice_runtime,
                "process_audio_file",
                new=AsyncMock(side_effect=[first_output, KeyboardInterrupt()]),
            ), patch.dict(os.environ, {"XIAOAN_VOICE_POST_TTS_DISCARD_SECONDS": "2.0"}):
                count = await voice_runtime.run_local_mic_loop(
                    runtime_factory=FakeRuntime,
                    output_stream=io.StringIO(),
                    error_stream=io.StringIO(),
                    db_path=":memory:",
                    duration_seconds=6.0,
                    asr_backend="fake",
                    output_dir=str(Path(temp_dir) / "audio"),
                    latest_output_path=str(latest_output),
                )
            latest = json.loads(latest_output.read_text(encoding="utf-8"))

        self.assertEqual(count, 1)
        recorder = FakePersistentRecorder.instances[0]
        self.assertEqual(recorder.discarded, [2.0])
        self.assertEqual(len(recorder.recorded), 2)
        self.assertTrue(recorder.closed)
        self.assertEqual(latest["event_type"], "voice.recording")
        self.assertEqual(latest["previous_output"]["event_type"], "voice.post_tts_discard")
        self.assertEqual(latest["previous_output"]["tts_text"], "你好，我在。")

    async def test_until_mic_off_mode_records_one_complete_segment_before_asr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "work_mode.json"
            WorkModeStore(state_path, cooldown_seconds=0).update_controls(
                system_enabled=True,
                mic_recognition_enabled=True,
                camera_capture_enabled=True,
            )
            ToggleOffRecorder.state_path = state_path
            output = {
                "event_type": "asr.transcript",
                "handled": True,
                "text": "小安帮我记录完整句子",
            }
            old_env = os.environ.get("XIAOAN_WORK_MODE_STATE_PATH")
            os.environ["XIAOAN_WORK_MODE_STATE_PATH"] = str(state_path)
            try:
                with patch.object(voice_runtime, "PersistentWavRecorder", ToggleOffRecorder), patch.object(
                    voice_runtime,
                    "list_input_devices",
                    return_value=[{
                        "backend": "pyaudio",
                        "index": 0,
                        "device_id": "0",
                        "name": "unit mic",
                        "max_input_channels": 1,
                        "default_sample_rate": 16000,
                    }],
                ), patch.object(voice_runtime, "create_asr_backend", return_value=CountingASRBackend()), patch.object(
                    voice_runtime,
                    "process_audio_file",
                    new=AsyncMock(return_value=output),
                ) as process_audio:
                    count = await voice_runtime.run_local_mic_loop(
                        runtime_factory=FakeRuntime,
                        output_stream=io.StringIO(),
                        error_stream=io.StringIO(),
                        db_path=":memory:",
                        once=True,
                        duration_seconds=6.0,
                        asr_backend="fake",
                        output_dir=str(Path(temp_dir) / "audio"),
                        capture_mode="until_mic_off",
                    )
            finally:
                if old_env is None:
                    os.environ.pop("XIAOAN_WORK_MODE_STATE_PATH", None)
                else:
                    os.environ["XIAOAN_WORK_MODE_STATE_PATH"] = old_env

        recorder = FakePersistentRecorder.instances[0]
        self.assertEqual(count, 1)
        self.assertEqual(len(recorder.recorded), 0)
        self.assertGreaterEqual(len(recorder.read_windows), 3)
        self.assertTrue(process_audio.await_args.kwargs["completed_mic_segment"])
        self.assertEqual(process_audio.await_args.kwargs["trim_speech"], True)

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
                "--work-mode-gated",
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
        self.assertTrue(kwargs["work_mode_gated"])


if __name__ == "__main__":
    unittest.main()
