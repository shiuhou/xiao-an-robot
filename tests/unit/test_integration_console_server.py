from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from base_station.integration_console.console_server import (
    AGENT_ACK_TIMEOUT_SECONDS,
    AGENT_TTS_ACK_TIMEOUT_SECONDS,
    IntegrationConsoleApp,
    create_server,
    _agent_ack_timeout_seconds,
    read_ws_state,
)
from base_station.integration_console.fast_demo_brain import DANCE_INTRO_TEXT, iter_fast_demo_tts_texts
from base_station.integration_console.story_demo import get_story_node


class FakeRunningProcess:
    pid = 12345

    def poll(self) -> None:
        return None


class FakeExitedProcess:
    pid = 12345

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode


class FakePopen(FakeRunningProcess):
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


class IntegrationConsoleHttpTest(unittest.TestCase):
    def test_console_html_contains_visual_trace_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server("127.0.0.1", 0, runtime_dir=temp_dir)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                with urllib.request.urlopen(f"http://{host}:{port}/console", timeout=5) as response:
                    html = response.read().decode("utf-8")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        for element_id in (
            "cameraLatestImage",
            "workModeSystemSwitch",
            "workModeMicRecognitionSwitch",
            "workModeCameraSwitch",
            "workModeStartBtn",
            "workModeStopBtn",
            "workModeStatus",
            "workLocalFastPaths",
            "workOpenclawPaths",
            "workWorkspaceKv",
            "workVisualLatestImage",
            "workVisualImageEmpty",
            "workAsrText",
            "workBrainReplyKv",
            "workBrainReplyText",
            "workVisualFreshness",
            "workVisualCvMetrics",
            "workVisualGateStatus",
            "workVisualGateRules",
            "workVisualVlmStatus",
            "workVisualVlmDetails",
            "workVisualFusion",
            "workRoutingKv",
            "workLocalReminderJson",
            "manualRobotStatus",
            "expressionButtons",
            "motionAction",
            "motionSpeed",
            "motionDistance",
            "motionAngle",
            "motionDuration",
            "motionTimeout",
            "sendMotionBtn",
            "manualRobotJson",
            "ttsRuntimeKv",
            "ttsPlaybackJson",
            "link1RunSwitch",
            "link1Steps",
            "link2RunSwitch",
            "link2Steps",
            "link3RunSwitch",
            "link3Steps",
            "visualLatestImage",
            "visualFreshness",
            "visualCvMetrics",
            "visualGateRules",
            "visualVlmStatus",
            "visualTriggerImage",
            "visualFusion",
            "link2OpenclawCareStatus",
            "link2OpenclawCareVoice",
            "link2OpenclawCareMeta",
            "link2AsrText",
            "link2OpenFaceJson",
            "link2VlmTriggerJson",
            "link2VlmRuntimeJson",
            "fastDemoSendRobotSwitch",
            "fastDemoAllowMotionSwitch",
            "fastReminderKv",
            "fastReminderJson",
            "storyStartBtn",
            "storyStopBtn",
            "storyStatus",
            "storyVoiceKv",
            "storyNodeText",
            "storyChoiceButtons",
            "storyJson",
            "fastDanceRunSwitch",
            "fastDanceStatus",
            "fastDanceSteps",
            "fastDanceMicKv",
            "fastDanceAsrText",
            "fastDanceJson",
            "fast1RunSwitch",
            "fast1Steps",
            "fast1BrainText",
            "fast2RunSwitch",
            "fast2Steps",
            "fast2BrainText",
            "fast2ExecuteBtn",
            "fast2VisualLatestImage",
            "fast2VisualFreshness",
            "fast2VisualCvMetrics",
            "fast2VisualGateStatus",
            "fast2VisualGateRules",
            "fast2VisualVlmStatus",
            "fast2VisualTriggerImage",
            "fast2VisualVlmDetails",
            "fast2VisualFusion",
            "fast3RunSwitch",
            "fast3Steps",
            "fast3BrainText",
        ):
            self.assertIn(f'id="{element_id}"', html)

    def test_single_shot_voice_links_are_not_labeled_resident_recording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server("127.0.0.1", 0, runtime_dir=temp_dir)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                with urllib.request.urlopen(f"http://{host}:{port}/console", timeout=5) as response:
                    html = response.read().decode("utf-8")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertIn('<input id="link1RunSwitch" type="checkbox"> 运行一次', html)
        self.assertIn('<input id="link3RunSwitch" type="checkbox"> 运行一次', html)

    def test_health_and_state_work_without_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server(
                "127.0.0.1",
                0,
                runtime_dir=temp_dir,
                ws_url="ws://127.0.0.1:8765/agent",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            base_url = f"http://{host}:{port}"
            try:
                with urllib.request.urlopen(f"{base_url}/api/health", timeout=5) as response:
                    health = json.loads(response.read().decode("utf-8"))
                with urllib.request.urlopen(f"{base_url}/api/state", timeout=5) as response:
                    state = json.loads(response.read().decode("utf-8"))
                state_file_exists = (Path(temp_dir) / "work_mode_state.json").exists()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertTrue(health["ok"])
        self.assertFalse(health["ws_state_exists"])
        self.assertTrue(state["ok"])
        self.assertFalse(state["ws_server"]["ok"])
        self.assertFalse(state["robot"]["online"])
        self.assertIn("tts_runtime", state)
        self.assertIn("latest_image", state["media"])
        self.assertIn("links", state)
        self.assertIn("processes", state)
        self.assertIn("link1", state["links"])
        self.assertIn("link2", state["links"])
        self.assertIn("link3", state["links"])
        self.assertIn("work_voice", state["processes"])
        self.assertIn("fast_demo", state)
        self.assertIn("work_mode", state)
        self.assertFalse(state["work_mode"]["state"]["system_enabled"])
        self.assertIn("local_fast_paths", state["work_mode"])
        self.assertIn("fast1", state["fast_demo"])
        self.assertIn("fast2", state["fast_demo"])
        self.assertIn("fast3", state["fast_demo"])
        self.assertFalse(state["processes"]["link2"]["running"])

    def test_work_mode_update_persists_to_state_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "base_station.integration_console.console_server.subprocess.Popen",
            side_effect=lambda *args, **kwargs: FakePopen(*args, **kwargs),
        ), patch("base_station.integration_console.console_server.time.sleep", return_value=None):
            server = create_server(
                "127.0.0.1",
                0,
                runtime_dir=temp_dir,
                ws_url="ws://127.0.0.1:8765/agent",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            base_url = f"http://{host}:{port}"
            try:
                body = json.dumps({
                    "system_enabled": True,
                    "mic_recognition_enabled": True,
                    "camera_capture_enabled": True,
                }).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/api/work-mode/update",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    update = json.loads(response.read().decode("utf-8"))
                with urllib.request.urlopen(f"{base_url}/api/state", timeout=5) as response:
                    state = json.loads(response.read().decode("utf-8"))
                state_file_exists = (Path(temp_dir) / "work_mode_state.json").exists()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertTrue(update["ok"])
        self.assertIn("voice", update)
        self.assertTrue(state["work_mode"]["state"]["system_enabled"])
        self.assertTrue(state["work_mode"]["state"]["mic_recognition_enabled"])
        self.assertTrue(state_file_exists)

    def test_state_ignores_stale_demo_files_for_link_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as workspace_dir:
            runtime = Path(temp_dir)
            workspace = Path(workspace_dir)
            state_dir = workspace / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "dashboard.json").write_text(
                json.dumps(
                    {
                        "schema": "xiaoan.dashboard.v1",
                        "updated_at": "2026-07-06T12:00:00",
                        "mode": "speaking",
                        "status_text": "屏幕显示内容",
                        "latest_reply": {
                            "display_text": "屏幕显示内容",
                            "spoken_text": "后续关怀语音",
                            "source": "unit-test",
                            "received_at": "2026-07-06T12:00:00",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (runtime / "latest_audio.pcm").write_bytes(b"\0" * 32)
            (runtime / "demo1_transcript.json").write_text(
                json.dumps({"transcript": "我有点累"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (runtime / "assistant_capture_result.json").write_text(
                json.dumps({"reply_text": "我在这里。"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (runtime / "ws_state.json").write_text(
                json.dumps(
                    {
                        "selected_device_id": "robot-1",
                        "sessions": {},
                        "devices": {},
                        "last_command_ack": {
                            "received_at": "2026-07-06T12:00:01+00:00",
                            "payload": {"status": "accepted"},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(
                runtime_dir=runtime,
                openclaw_workspace=workspace,
            )
            state = app.state()

        self.assertTrue(state["openclaw_dashboard"]["ok"])
        self.assertEqual(
            state["openclaw_dashboard"]["dashboard"]["latest_reply"]["display_text"],
            "屏幕显示内容",
        )
        self.assertNotEqual(state["links"]["link1"]["status"], "complete")
        self.assertNotEqual(state["links"]["link3"]["status"], "complete")
        self.assertEqual(state["links"]["link1"]["asr_text"], "我有点累")

    def test_link_completion_uses_current_managed_voice_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as workspace_dir:
            runtime = Path(temp_dir)
            workspace = Path(workspace_dir)
            state_dir = workspace / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "dashboard.json").write_text(
                json.dumps(
                    {
                        "schema": "xiaoan.dashboard.v1",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "mode": "speaking",
                        "status_text": "提醒创建完成",
                        "latest_reply": {
                            "display_text": "提醒创建完成",
                            "spoken_text": "一分钟后提醒你喝水",
                            "source": "unit-test",
                            "received_at": datetime.now(timezone.utc).isoformat(),
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            audio_path = runtime / "voice.wav"
            audio_path.write_bytes(b"RIFF")
            latest_dir = runtime / "integration_console" / "link1"
            latest_dir.mkdir(parents=True)
            (latest_dir / "latest_voice.json").write_text(
                json.dumps(
                    {
                        "text": "小安一分钟后提醒我喝水",
                        "reply_text": "一分钟后提醒你喝水。",
                        "event": {
                            "type": "asr.transcript",
                            "payload": {
                                "audio": {
                                    "audio_path": str(audio_path),
                                    "sample_rate": 16000,
                                    "duration_ms": 6000,
                                }
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (runtime / "ws_state.json").write_text(
                json.dumps(
                    {
                        "selected_device_id": "robot-1",
                        "sessions": {},
                        "devices": {},
                        "last_command_ack": {
                            "received_at": datetime.now(timezone.utc).isoformat(),
                            "payload": {"status": "accepted"},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(
                runtime_dir=runtime,
                openclaw_workspace=workspace,
            )
            app.link_processes["link1"] = FakeExitedProcess(0)
            state = app.state()

        self.assertEqual(state["links"]["link1"]["status"], "complete")
        self.assertFalse(state["processes"]["link1"]["running"])
        self.assertEqual(state["processes"]["link1"]["returncode"], 0)
        self.assertEqual(state["links"]["link1"]["asr_text"], "小安一分钟后提醒我喝水")
        self.assertEqual(state["links"]["link1"]["openclaw_text"], "一分钟后提醒你喝水。")

    def test_latest_image_missing_returns_structured_404(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server("127.0.0.1", 0, runtime_dir=temp_dir)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(f"http://{host}:{port}/api/latest-image", timeout=5)
                payload = json.loads(raised.exception.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(raised.exception.code, 404)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "not_found")

    def test_visual_endpoints_serve_state_and_owned_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            visual_dir = Path(temp_dir) / "integration_console" / "visual"
            visual_dir.mkdir(parents=True)
            (visual_dir / "latest_state.json").write_text(
                json.dumps({"schema_version": "visual_console_v1", "snapshot_id": "frame-7"}),
                encoding="utf-8",
            )
            (visual_dir / "latest_annotated.jpg").write_bytes(b"latest-jpeg")
            (visual_dir / "vlm_trigger.jpg").write_bytes(b"trigger-jpeg")
            server = create_server("127.0.0.1", 0, runtime_dir=temp_dir)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            base_url = f"http://{host}:{port}"
            try:
                with urllib.request.urlopen(f"{base_url}/api/visual/state", timeout=5) as response:
                    state = json.loads(response.read().decode("utf-8"))
                with urllib.request.urlopen(f"{base_url}/api/visual/latest-image", timeout=5) as response:
                    latest = response.read()
                    cache_control = response.headers["Cache-Control"]
                with urllib.request.urlopen(f"{base_url}/api/visual/trigger-image", timeout=5) as response:
                    trigger = response.read()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertTrue(state["ok"])
        self.assertEqual(state["freshness"], "live")
        self.assertEqual(state["state"]["snapshot_id"], "frame-7")
        self.assertEqual(latest, b"latest-jpeg")
        self.assertEqual(trigger, b"trigger-jpeg")
        self.assertIn("no-store", cache_control)

    def test_fast_demo_visual_endpoints_serve_owned_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            visual_dir = Path(temp_dir) / "integration_console" / "fast_demo" / "visual"
            visual_dir.mkdir(parents=True)
            (visual_dir / "latest_annotated.jpg").write_bytes(b"fast-latest-jpeg")
            (visual_dir / "vlm_trigger.jpg").write_bytes(b"fast-trigger-jpeg")
            server = create_server("127.0.0.1", 0, runtime_dir=temp_dir)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            base_url = f"http://{host}:{port}"
            try:
                with urllib.request.urlopen(f"{base_url}/api/fast-demo/visual/latest-image", timeout=5) as response:
                    latest = response.read()
                with urllib.request.urlopen(f"{base_url}/api/fast-demo/visual/trigger-image", timeout=5) as response:
                    trigger = response.read()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(latest, b"fast-latest-jpeg")
        self.assertEqual(trigger, b"fast-trigger-jpeg")

    def test_fast_demo_visual_stale_running_vlm_does_not_drive_decision(self) -> None:
        trace = {
            "frame_id": 40,
            "observation": {"face_detected": True},
            "cv_sample": {
                "emotion_tag": "stressed",
                "confidence": 0.43,
                "fatigue_score": 100,
            },
            "gate": {
                "result": {
                    "should_trigger": True,
                    "reason": "force",
                },
            },
            "vlm": {
                "status": "running",
                "request_id": "vlm-old",
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            visual = {
                "ok": True,
                "freshness": "stale",
                "age_ms": 120000,
                "state": trace,
                "files": {
                    "latest_image": {
                        "exists": True,
                        "age_ms": 120000,
                    },
                },
            }
            result = app._fast_demo_visual_link_state(visual, {"fast2": {"running": False}})

        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["brain_text"], "")
        self.assertEqual(result["decision"], {})
        self.assertEqual(result["robot_plan"], {})
        self.assertEqual(result["steps"][2]["detail"]["vlm_status"], "stale_running")


class IntegrationConsoleCommandTest(unittest.TestCase):
    def test_tts_agent_ack_timeout_allows_slow_synthesis(self) -> None:
        self.assertEqual(
            _agent_ack_timeout_seconds({"command": "audio.play_tts"}),
            AGENT_TTS_ACK_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            _agent_ack_timeout_seconds({"command": "audio.play_local"}),
            AGENT_ACK_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            _agent_ack_timeout_seconds({"command": "display.expression"}),
            AGENT_ACK_TIMEOUT_SECONDS,
        )

    def test_link_commands_are_fixed_runtime_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            link1 = app.link_command("link1")
            link2 = app.link_command("link2")
            link3 = app.link_command("link3")

        self.assertIn("base_station.monitor.voice_runtime", link1)
        self.assertIn("--source", link1)
        self.assertIn("local_mic", link1)
        self.assertIn("base_station.monitor.emotion_runtime", link2)
        self.assertIn("ws_video_observer", link2)
        self.assertIn("--enable-vlm-gate", link2)
        self.assertIn("--latest-output", link1)
        self.assertIn("--asr-language", link1)
        self.assertIn("--once", link1)
        self.assertIn("--once", link3)
        self.assertNotIn("--work-mode-gated", link1)
        self.assertNotIn("--work-mode-gated", link3)
        self.assertEqual(link1[link1.index("--duration") + 1], "6.0")
        self.assertEqual(link3[link3.index("--duration") + 1], "6.0")
        self.assertNotIn("--once", link2)
        self.assertIn("--disable-companion-fast-path", link1)
        self.assertNotIn("--disable-companion-fast-path", link3)
        self.assertIn("--local-demo-reminders-path", link1)
        self.assertEqual(
            link1[link1.index("--local-demo-reminders-path") + 1],
            str(app.fast_demo_reminders_path),
        )
        self.assertNotIn("--local-demo-reminders-path", link3)
        self.assertIn("openface_ov", link2)
        self.assertIn("openvino_qwen_vl", link2)
        self.assertEqual(link2[link2.index("--vlm-max-new-tokens") + 1], "128")
        self.assertEqual(link2[link2.index("--device") + 1], "NPU")
        self.assertEqual(link2[link2.index("--vlm-device") + 1], "GPU")
        self.assertNotIn("--preload-vlm", link2)
        self.assertEqual(
            link2[link2.index("--vlm-model-path") + 1],
            "base_station/models/Qwen2.5-VL-3B-OV-int4",
        )
        self.assertNotIn("--force-vlm", link2)
        self.assertIn("base_station.monitor.voice_runtime", link3)

    def test_link2_vlm_preload_is_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"XIAOAN_LINK2_PRELOAD_VLM": "1"},
        ):
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            link2 = app.link_command("link2")

        self.assertIn("--enable-vlm-gate", link2)
        self.assertIn("--preload-vlm", link2)
        self.assertNotIn("--force-vlm", link2)

    def test_work_voice_command_is_real_resident_openclaw_voice_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            command = app.link_command("work_voice")
            env = app.link_environment("work_voice")

        self.assertIn("base_station.monitor.voice_runtime", command)
        self.assertIn("local_mic", command)
        self.assertNotIn("--once", command)
        self.assertIn("--work-mode-gated", command)
        self.assertNotIn("--decision-mode", command)
        self.assertEqual(command[command.index("--capture-mode") + 1], "until_mic_off")
        self.assertIn("--latest-output", command)
        self.assertIn("work_voice", command[command.index("--latest-output") + 1])
        self.assertEqual(env["XIAO_AN_OPENCLAW_BACKEND"], "gateway")
        self.assertEqual(env["XIAO_AN_OPENCLAW_AGENT"], "xiaoan-runtime")
        self.assertIn("XIAOAN_WORK_MODE_STATE_PATH", env)

    def test_start_work_mode_starts_voice_and_visual_processes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "base_station.integration_console.console_server.subprocess.Popen",
            side_effect=lambda *args, **kwargs: FakePopen(*args, **kwargs),
        ), patch("base_station.integration_console.console_server.time.sleep", return_value=None):
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            result = app.start_work_mode({
                "mic_recognition_enabled": True,
                "camera_capture_enabled": True,
            })

        self.assertTrue(result["ok"])
        self.assertTrue(result["work_mode"]["system_enabled"])
        self.assertIn("work_voice", app.link_processes)
        self.assertIn("link2", app.link_processes)

    def test_work_voice_and_single_shot_voice_links_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.link_processes["work_voice"] = FakeRunningProcess()
            link_result = app.start_link({"link": "link1"})
            fast_result = app.start_fast_demo({"link": "fast3"})

        self.assertFalse(link_result["ok"])
        self.assertEqual(link_result["error"], "work_mode_running_use_stop_first")
        self.assertFalse(fast_result["ok"])
        self.assertEqual(fast_result["error"], "work_mode_running_use_stop_first")

    def test_start_work_mode_is_blocked_by_single_shot_voice_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.link_processes["link3"] = FakeRunningProcess()
            result = app.start_work_mode({
                "mic_recognition_enabled": True,
                "camera_capture_enabled": False,
            })

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "single_shot_link_running:link3")
        self.assertFalse(result["work_mode"]["system_enabled"])
        self.assertNotIn("work_voice", app.link_processes)

    def test_update_work_mode_is_blocked_by_fast_demo_voice_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.link_processes["fast1"] = FakeRunningProcess()
            result = app.update_work_mode({
                "system_enabled": True,
                "mic_recognition_enabled": True,
                "camera_capture_enabled": False,
            })

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "single_shot_link_running:fast1")
        self.assertFalse(result["work_mode"]["system_enabled"])
        self.assertNotIn("work_voice", app.link_processes)

    def test_work_mode_update_restarts_missing_voice_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "base_station.integration_console.console_server.subprocess.Popen",
            side_effect=lambda *args, **kwargs: FakePopen(*args, **kwargs),
        ), patch("base_station.integration_console.console_server.time.sleep", return_value=None):
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            result = app.update_work_mode({
                "system_enabled": True,
                "mic_recognition_enabled": True,
                "camera_capture_enabled": False,
            })

        self.assertTrue(result["ok"])
        self.assertIn("voice", result)
        self.assertIn("work_voice", app.link_processes)
        self.assertNotIn("link2", app.link_processes)

    def test_work_mode_state_exposes_routing_policy_and_link2_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            workspace = runtime / "workspace-xiaoan-runtime"
            visual_dir = runtime / "integration_console" / "visual"
            visual_dir.mkdir(parents=True)
            (runtime / "latest.jpg").write_bytes(b"cached-camera-frame")
            (visual_dir / "latest_annotated.jpg").write_bytes(b"live-link2-frame")
            (visual_dir / "latest_state.json").write_text(
                json.dumps(
                    {
                        "frame_id": 7,
                        "observation": {"face_detected": True, "ear": 0.21},
                        "cv_sample": {"emotion_tag": "tired", "confidence": 0.91, "fatigue_score": 0.8},
                        "gate": {"result": {"should_trigger": True, "reason": "high_fatigue"}},
                        "vlm": {
                            "status": "done",
                            "request_id": "vlm-1",
                            "trigger_frame_id": 7,
                            "result": {"expression_label": "tired"},
                            "fusion": {"decision": "cv_vlm_agree_negative"},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            work_voice_dir = runtime / "integration_console" / "work_voice"
            work_voice_dir.mkdir(parents=True)
            (work_voice_dir / "latest_voice.json").write_text(
                json.dumps({"text": "小安在吗", "event_type": "asr.transcript"}, ensure_ascii=False),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime, openclaw_workspace=workspace)

            state = app.state()
            work = state["work_mode"]

        self.assertEqual(work["routing_policy"]["mode"], "local_fast_path_first_then_openclaw")
        self.assertEqual(work["diagnostics"]["asr_text"], "小安在吗")
        self.assertEqual(work["diagnostics"]["openface"]["frame_id"], 7)
        self.assertTrue(work["diagnostics"]["vlm_gate"]["should_trigger"])
        self.assertEqual(work["diagnostics"]["vlm_runtime"]["request_id"], "vlm-1")
        self.assertEqual(work["cards"]["camera"]["latest_image_source"], "link2_visual_trace")
        self.assertIn("integration_console/visual/latest_annotated.jpg", work["cards"]["camera"]["latest_image_path"])
        self.assertEqual(state["links"]["camera"]["latest_image_source"], "link2_visual_trace")
        self.assertIn("integration_console/visual/latest_annotated.jpg", state["links"]["camera"]["latest_image"]["path"])
        self.assertEqual(work["workspace"]["dashboard"], str(workspace / "state" / "dashboard.json"))
        self.assertEqual(work["workspace"]["local_reminders"], str(workspace / "state" / "local_reminders.json"))

    def test_work_mode_diagnostics_prefers_work_voice_previous_output_over_stale_link1(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            work_voice_dir = runtime / "integration_console" / "work_voice"
            link1_dir = runtime / "integration_console" / "link1"
            work_voice_dir.mkdir(parents=True)
            link1_dir.mkdir(parents=True)
            (work_voice_dir / "latest_voice.json").write_text(
                json.dumps(
                    {
                        "event_type": "voice.muted",
                        "reason": "mic_recognition_disabled",
                        "text": "",
                        "previous_output": {
                            "event_type": "asr.transcript",
                            "text": "小安在吗",
                            "reply_text": "我在。",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (link1_dir / "latest_voice.json").write_text(
                json.dumps(
                    {
                        "event_type": "asr.transcript",
                        "text": "小安，帮我在飞猪上创立一个文档，你导小安小安。",
                        "reply_text": "已在飞书创建文档：小安小安",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime)

            state = app.state()

        self.assertEqual(state["work_mode"]["diagnostics"]["asr_text"], "小安在吗")

    def test_work_mode_diagnostics_does_not_fallback_to_stale_link_voice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            work_voice_dir = runtime / "integration_console" / "work_voice"
            link1_dir = runtime / "integration_console" / "link1"
            work_voice_dir.mkdir(parents=True)
            link1_dir.mkdir(parents=True)
            (work_voice_dir / "latest_voice.json").write_text(
                json.dumps(
                    {
                        "event_type": "voice.muted",
                        "reason": "mic_recognition_disabled",
                        "text": "",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (link1_dir / "latest_voice.json").write_text(
                json.dumps(
                    {
                        "event_type": "asr.transcript",
                        "text": "小安，帮我在飞猪上创立一个文档，你导小安小安。",
                        "reply_text": "已在飞书创建文档：小安小安",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime)

            state = app.state()

        self.assertEqual(state["work_mode"]["diagnostics"]["asr_text"], "")
        self.assertNotIn("飞猪", state["work_mode"]["cards"]["asr_text"]["detail"])

    def test_work_mode_asr_card_explains_until_mic_off_recording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.work_mode_store.update_controls(
                system_enabled=True,
                mic_recognition_enabled=True,
                camera_capture_enabled=False,
            )
            app.link_processes["work_voice"] = FakeRunningProcess()

            state = app.state()
            asr_card = state["work_mode"]["cards"]["asr_text"]

        self.assertTrue(asr_card["ok"])
        self.assertEqual(asr_card["status_label"], "RECORDING")
        self.assertIn("关闭麦克风识别后转写", asr_card["detail"])

    def test_work_mode_asr_card_warns_when_voice_runtime_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.work_mode_store.update_controls(
                system_enabled=True,
                mic_recognition_enabled=True,
                camera_capture_enabled=False,
            )

            state = app.state()
            asr_card = state["work_mode"]["cards"]["asr_text"]

        self.assertFalse(asr_card["ok"])
        self.assertEqual(asr_card["status_label"], "VOICE OFF")
        self.assertIn("语音 runtime 未运行", asr_card["detail"])

    def test_work_mode_state_recovers_stale_running_episode_when_process_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.work_mode_store.update_controls(
                system_enabled=True,
                mic_recognition_enabled=True,
                camera_capture_enabled=False,
            )
            lease = app.work_mode_store.acquire_episode(
                chain="link1",
                source="asr",
                text="帮我查一下天气",
                requires_mic_recognition=True,
            )

            state = app.state()

        self.assertTrue(lease.acquired)
        work_state = state["work_mode"]["state"]
        self.assertEqual(work_state["episode_state"], "idle")
        self.assertIsNone(work_state["active_run_id"])
        self.assertEqual(work_state["last_episode"]["status"], "interrupted")
        self.assertEqual(work_state["last_episode"]["result"]["reason"], "link1_process_missing")

    def test_voice_link_commands_accept_mic_device_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {
                "XIAOAN_LINK1_MIC_DEVICE": "default",
                "XIAOAN_FAST_DEMO_MIC_DEVICE": "plughw:0,0",
            },
        ):
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            link1 = app.link_command("link1")
            fast1 = app.fast_demo_command("fast1", {})

        self.assertEqual(link1[link1.index("--device") + 1], "default")
        self.assertEqual(fast1[fast1.index("--device") + 1], "plughw:0,0")

    def test_link_environment_defaults_to_openclaw_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            app = IntegrationConsoleApp(
                runtime_dir=temp_dir,
                openclaw_url="ws://127.0.0.1:18789",
            )
            link1_env = app.link_environment("link1")
            link2_env = app.link_environment("link2")
            link3_env = app.link_environment("link3")

        self.assertEqual(link1_env["XIAO_AN_OPENCLAW_BACKEND"], "gateway")
        self.assertEqual(link1_env["XIAO_AN_OPENCLAW_GATEWAY_URL"], "ws://127.0.0.1:18789")
        self.assertEqual(link1_env["XIAO_AN_OPENCLAW_AGENT"], "xiaoan-runtime")
        self.assertNotIn("XIAO_AN_OPENCLAW_FRESH_WORK_CAPTURE_SESSION", link1_env)
        self.assertEqual(link2_env["XIAO_AN_OPENCLAW_BACKEND"], "gateway")
        self.assertEqual(link2_env["XIAO_AN_OPENCLAW_GATEWAY_URL"], "ws://127.0.0.1:18789")
        self.assertEqual(link2_env["XIAO_AN_OPENCLAW_AGENT"], "xiaoan-runtime")
        self.assertNotIn("XIAO_AN_OPENCLAW_FRESH_WORK_CAPTURE_SESSION", link2_env)
        self.assertEqual(link3_env["XIAO_AN_OPENCLAW_BACKEND"], "gateway")
        self.assertEqual(link3_env["XIAO_AN_OPENCLAW_GATEWAY_URL"], "ws://127.0.0.1:18789")
        self.assertEqual(link3_env["XIAO_AN_OPENCLAW_AGENT"], "xiaoan-runtime")
        self.assertNotIn("XIAO_AN_OPENCLAW_FRESH_WORK_CAPTURE_SESSION", link3_env)

    def test_fast_demo_commands_keep_inference_and_skip_openclaw_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            fast1 = app.fast_demo_command("fast1", {"send_to_robot": True, "allow_motion": False})
            fast2 = app.fast_demo_command("fast2", {})
            fast3 = app.fast_demo_command("fast3", {"send_to_robot": True, "allow_motion": True})

        self.assertIn("base_station.monitor.voice_runtime", fast1)
        self.assertIn("--decision-mode", fast1)
        self.assertEqual(fast1[fast1.index("--decision-mode") + 1], "local_demo")
        self.assertEqual(fast1[fast1.index("--local-demo-link") + 1], "fast1")
        self.assertIn("--local-demo-send-to-robot", fast1)
        self.assertNotIn("--local-demo-allow-motion", fast1)
        self.assertIn("--local-demo-reminders-path", fast1)
        self.assertIn("--once", fast1)
        self.assertEqual(fast1[fast1.index("--duration") + 1], "6.0")

        self.assertIn("base_station.monitor.emotion_runtime", fast2)
        self.assertIn("ws_video_observer", fast2)
        self.assertIn("--enable-vlm-gate", fast2)
        self.assertIn("--no-agent", fast2)
        self.assertNotIn("--force-vlm", fast2)
        self.assertEqual(fast2[fast2.index("--visual-trace-fps") + 1], "5.0")
        self.assertEqual(fast2[fast2.index("--vlm-min-interval-seconds") + 1], "8.0")
        self.assertEqual(fast2[fast2.index("--vlm-max-new-tokens") + 1], "128")
        self.assertEqual(fast2[fast2.index("--device") + 1], "NPU")
        self.assertEqual(fast2[fast2.index("--vlm-device") + 1], "GPU")
        self.assertIn("--preload-vlm", fast2)
        self.assertTrue(fast2[fast2.index("--visual-trace-dir") + 1].endswith("integration_console/fast_demo/visual"))

        self.assertEqual(fast3[fast3.index("--local-demo-link") + 1], "fast3")
        self.assertIn("--local-demo-send-to-robot", fast3)
        self.assertIn("--local-demo-allow-motion", fast3)
        self.assertEqual(fast3[fast3.index("--duration") + 1], "6.0")

    def test_fast_demo_tts_prewarm_command_targets_local_cache_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            command = app.fast_demo_tts_prewarm_command()
            state = app.fast_demo_tts_prewarm_state()

        self.assertIn("tools/ops/prepare_fast_demo_tts.py", command)
        self.assertIn("--runtime-dir", command)
        self.assertEqual(command[command.index("--runtime-dir") + 1], temp_dir)
        self.assertIn("--manifest-path", command)
        self.assertTrue(command[command.index("--manifest-path") + 1].endswith("integration_console/fast_demo/tts_manifest.json"))
        self.assertFalse(state["managed"])
        self.assertEqual(state["status"], "disabled")

    def test_fast2_visual_prewarm_starts_visual_runtime_without_robot_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "base_station.integration_console.console_server.subprocess.Popen",
            side_effect=FakePopen,
        ), patch("base_station.integration_console.console_server.time.sleep", return_value=None):
            app = IntegrationConsoleApp(runtime_dir=temp_dir, prewarm_fast2_visual=True)

        state = app.fast2_visual_prewarm_state()
        self.assertTrue(state["managed"])
        self.assertTrue(state["running"])
        self.assertFalse(state["send_to_robot"])
        self.assertFalse(state["allow_motion"])
        self.assertIn("fast2", app.link_processes)
        command = app.link_processes["fast2"].args[0]
        self.assertIn("base_station.monitor.emotion_runtime", command)
        self.assertEqual(command[command.index("--device") + 1], "NPU")
        self.assertEqual(command[command.index("--vlm-device") + 1], "GPU")
        self.assertIn("--preload-vlm", command)

    def test_health_exposes_fast2_visual_prewarm_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)

        health = app.health()

        self.assertIn("fast2_visual_prewarm", health)
        self.assertFalse(health["fast2_visual_prewarm"]["managed"])

    def test_fast_demo_environment_removes_openclaw_runtime_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {
                "XIAO_AN_OPENCLAW_BACKEND": "gateway",
                "XIAO_AN_OPENCLAW_GATEWAY_URL": "ws://127.0.0.1:18789",
                "XIAO_AN_OPENCLAW_AGENT": "xiaoan-runtime",
            },
            clear=True,
        ):
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            env = app.fast_demo_environment()

        self.assertNotIn("XIAO_AN_OPENCLAW_BACKEND", env)
        self.assertNotIn("XIAO_AN_OPENCLAW_GATEWAY_URL", env)
        self.assertNotIn("XIAO_AN_OPENCLAW_AGENT", env)

    def test_link_state_displays_previous_voice_result_while_recording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            latest_dir = runtime / "integration_console" / "link1"
            latest_dir.mkdir(parents=True)
            (latest_dir / "latest_voice.json").write_text(
                json.dumps(
                    {
                        "event_type": "voice.recording",
                        "reason": "recording",
                        "text": "",
                        "previous_output": {
                            "text": "小安一分钟后提醒我喝水",
                            "reply_text": "一分钟后提醒你喝水。",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime)
            app.link_processes["link1"] = FakeRunningProcess()

            state = app.state()

        self.assertEqual(state["links"]["link1"]["asr_text"], "小安一分钟后提醒我喝水")
        self.assertEqual(state["links"]["link1"]["openclaw_text"], "一分钟后提醒你喝水。")
        self.assertEqual(state["links"]["link1"]["voice_phase"]["mic"], "on")
        self.assertEqual(state["links"]["link1"]["voice_phase"]["phase"], "recording")

    def test_link_state_shows_asr_text_while_openclaw_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            latest_dir = runtime / "integration_console" / "link1"
            latest_dir.mkdir(parents=True)
            (latest_dir / "latest_voice.json").write_text(
                json.dumps(
                    {
                        "event_type": "asr.transcript",
                        "reason": "openclaw_pending",
                        "text": "小安一分钟后提醒我喝水",
                        "reply_text": "",
                        "display_text": "",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime)
            app.link_processes["link1"] = FakeRunningProcess()

            state = app.state()

        self.assertEqual(state["links"]["link1"]["asr_text"], "小安一分钟后提醒我喝水")
        self.assertEqual(state["links"]["link1"]["openclaw_text"], "")
        self.assertEqual(state["links"]["link1"]["voice_phase"]["mic"], "off")
        self.assertEqual(state["links"]["link1"]["voice_phase"]["phase"], "openclaw_pending")

    def test_link2_state_exposes_openclaw_care_voice_from_runtime_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            log_dir = runtime / "integration_console" / "process_logs"
            log_dir.mkdir(parents=True)
            (log_dir / "link2.log").write_text(
                """
[emotion.sample] {"payload": {"frame_id": 17, "emotion_tag": "tired", "fatigue_score": 88.0}}
{
  "openclaw_result": {
    "executed_actions": [
      {
        "name": "xiaoan.robot.care",
        "arguments": {
          "text": "辛苦啦，先放下手里的事，喝口水，休息一分钟就好。",
          "reason": "emotion.intervention"
        }
      }
    ]
  }
}
""",
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime)
            app.link_processes["link2"] = FakeRunningProcess()

            state = app.state()

        care_voice = state["links"]["link2"]["openclaw_care_voice"]
        self.assertTrue(care_voice["ok"])
        self.assertEqual(care_voice["text"], "辛苦啦，先放下手里的事，喝口水，休息一分钟就好。")
        self.assertEqual(care_voice["frame_id"], 17)
        self.assertEqual(care_voice["emotion_tag"], "tired")
        self.assertEqual(care_voice["fatigue_score"], 88.0)
        self.assertIn("OpenClaw 关怀语音", [step["label"] for step in state["links"]["link2"]["steps"]])

    def test_start_link_rejects_unknown_link_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            result = app.start_link({"link": "echo hacked"})

        self.assertFalse(result["ok"])
        self.assertIn("unsupported_link", result["error"])

    def test_start_fast_demo_rejects_unknown_link_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            result = app.start_fast_demo({"link": "echo hacked"})

        self.assertFalse(result["ok"])
        self.assertIn("unsupported_fast_demo_link", result["error"])

    def test_execute_fast_demo_visual_plan_respects_motion_switch(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            visual_dir = runtime / "integration_console" / "fast_demo" / "visual"
            visual_dir.mkdir(parents=True)
            (visual_dir / "latest_state.json").write_text(
                json.dumps(
                    {
                        "observation": {"face_detected": True},
                        "cv_sample": {"emotion_tag": "tired", "confidence": 0.92, "fatigue_score": 0.84},
                        "gate": {"result": {"should_trigger": True, "reason": "fatigue"}},
                        "vlm": {"status": "done", "result": {"expression_label": "tired"}},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime, command_sender=sender)
            result = app.execute_fast_demo_plan({
                "link": "fast2",
                "send_to_robot": True,
                "allow_motion": False,
            })

        self.assertTrue(result["ok"])
        self.assertEqual([payload["command"] for payload in sent], ["display.expression", "audio.play_tts"])
        self.assertTrue(any(step.get("reason") == "motion_disabled" for step in result["steps"]))

    def test_fast2_visual_care_auto_executes_when_robot_send_enabled(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            app = IntegrationConsoleApp(runtime_dir=runtime, command_sender=sender)
            app.fast_demo_options["fast2"] = {"send_to_robot": True, "allow_motion": False}
            visual = {
                "ok": True,
                "age_ms": 0,
                "freshness": {"age_ms": 0},
                "files": {"latest_image": {"exists": True, "mtime": 123.0, "age_ms": 0}},
                "state": {
                    "frame_id": 42,
                    "observation": {"face_detected": True},
                    "cv_sample": {"emotion_tag": "tired", "confidence": 0.92, "fatigue_score": 0.84},
                    "gate": {"result": {"should_trigger": True, "reason": "fatigue"}},
                    "vlm": {"status": "done", "request_id": "req-1", "result": {"expression_label": "tired"}},
                },
            }

            state = app._fast_demo_visual_link_state(visual, {"fast2": {"running": True, "pid": 123}})
            deadline = time.time() + 2
            while len(sent) < 2 and time.time() < deadline:
                time.sleep(0.01)

        self.assertEqual(state["decision"]["intent"], "visual_care")
        self.assertEqual(state["robot_execution"]["status"], "started")
        self.assertEqual([payload["command"] for payload in sent], ["display.expression", "audio.play_tts"])

    def test_fast2_visual_care_auto_executes_motion_only_when_allowed(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            app.fast_demo_options["fast2"] = {"send_to_robot": True, "allow_motion": True}
            app._wait_motion_completed = lambda *args, **kwargs: None  # type: ignore[method-assign]
            visual = {
                "ok": True,
                "age_ms": 0,
                "freshness": {"age_ms": 0},
                "files": {"latest_image": {"exists": True, "mtime": 124.0, "age_ms": 0}},
                "state": {
                    "frame_id": 43,
                    "observation": {"face_detected": True},
                    "cv_sample": {"emotion_tag": "tired", "confidence": 0.92, "fatigue_score": 0.84},
                    "gate": {"result": {"should_trigger": True, "reason": "fatigue"}},
                    "vlm": {"status": "done", "request_id": "req-2", "result": {"expression_label": "tired"}},
                },
            }

            app._fast_demo_visual_link_state(visual, {"fast2": {"running": True, "pid": 123}})
            deadline = time.time() + 2
            while len(sent) < 3 and time.time() < deadline:
                time.sleep(0.01)

        self.assertEqual([payload["command"] for payload in sent], ["display.expression", "motion.execute", "audio.play_tts"])

    def test_process_due_fast_demo_reminder_moves_out_once(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            reminder_path = runtime / "integration_console" / "fast_demo" / "reminders.json"
            reminder_path.parent.mkdir(parents=True)
            reminder_path.write_text(
                json.dumps(
                    {
                        "schema_version": "xiaoan.fast_demo_reminders.v1",
                        "items": [
                            {
                                "id": "fast-reminder-unit",
                                "status": "pending",
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "due_at": datetime.now(timezone.utc).isoformat(),
                                "transcript": "小安，10秒后提醒我喝水",
                                "send_to_robot": True,
                                "allow_motion": True,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime, command_sender=sender)
            app._wait_motion_completed = lambda steps, action_id, timeout_ms: steps.append({
                "name": "wait:motion.completed",
                "ok": True,
                "result": {"action_id": action_id},
            })
            first = app.process_due_fast_demo_reminders()
            second = app.process_due_fast_demo_reminders()
            saved = json.loads(reminder_path.read_text(encoding="utf-8"))

        self.assertEqual(first["processed"], 1)
        self.assertEqual(second["processed"], 0)
        self.assertEqual(saved["items"][0]["status"], "fired")
        self.assertIn("fired_at", saved["items"][0])
        self.assertEqual(
            [payload["command"] for payload in sent],
            ["display.expression", "motion.execute", "audio.play_tts"],
        )
        self.assertEqual(sent[1]["action"], "move_out_of_dock")
        self.assertEqual(sent[1]["params"]["distance_cm"], 8.0)

    def test_process_due_local_fast_path_reminder_uses_workspace_queue(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            workspace = runtime / "workspace-xiaoan-runtime"
            reminder_path = workspace / "state" / "local_reminders.json"
            reminder_path.parent.mkdir(parents=True)
            reminder_path.write_text(
                json.dumps(
                    {
                        "schema_version": "xiaoan.local_reminders.v1",
                        "items": [
                            {
                                "id": "local-reminder-unit",
                                "status": "pending",
                                "captured_at": datetime.now(timezone.utc).isoformat(),
                                "due_at": datetime.now(timezone.utc).isoformat(),
                                "title": "喝水",
                                "transcript": "小安，10秒后提醒我喝水",
                                "send_to_robot": True,
                                "allow_motion": False,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime, openclaw_workspace=workspace, command_sender=sender)
            app._wait_motion_completed = lambda steps, action_id, timeout_ms: steps.append({
                "name": "wait:motion.completed",
                "ok": True,
                "result": {"action_id": action_id},
            })

            first = app.process_due_local_fast_path_reminders()
            second = app.process_due_local_fast_path_reminders()
            saved = json.loads(reminder_path.read_text(encoding="utf-8"))

        self.assertEqual(first["processed"], 1)
        self.assertEqual(second["processed"], 0)
        self.assertEqual(saved["items"][0]["status"], "fired")
        self.assertEqual([payload["command"] for payload in sent], ["display.expression", "audio.play_tts"])

    def test_fast_demo_story_start_and_choice_update_state_without_fast3_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            app = IntegrationConsoleApp(runtime_dir=runtime)

            started = app.start_fast_demo_story({"send_to_robot": False})
            chosen = app.choose_fast_demo_story({"choice": "齿轮", "send_to_robot": False})
            state = app.fast_demo_story_state()
            saved = json.loads(app.fast_demo_story_path.read_text(encoding="utf-8"))

        self.assertTrue(started["ok"])
        self.assertTrue(chosen["ok"])
        self.assertEqual(chosen["choice"]["id"], "gear")
        self.assertEqual(state["current_node"]["id"], "gear")
        self.assertEqual(saved["current_node"], "gear")
        self.assertTrue(chosen["execution"]["skipped"])

    def test_fast_demo_story_sends_expression_and_tts_when_enabled(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.start_fast_demo_story({"send_to_robot": True})

        self.assertTrue(result["ok"])
        self.assertEqual([payload["command"] for payload in sent], ["display.expression", "audio.play_tts"])
        self.assertIn("月亮门", sent[1]["text"])
        self.assertEqual(sent[1]["playback_mode"], "buffered")

    def test_fast_demo_story_guard_allows_original_long_intro_pcm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            manifest_path = runtime / "integration_console" / "fast_demo" / "tts_manifest.json"
            manifest_path.parent.mkdir(parents=True)
            app = IntegrationConsoleApp(runtime_dir=runtime)
            intro = get_story_node("intro").text
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "xiaoan.fast_demo_tts_manifest.v2",
                        "items": [
                            {
                                "link": "story",
                                "intent": "intro",
                                "text": intro,
                                "pcm_bytes": 485376,
                                "duration_ms": 15168,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            ok, guard = app._story_tts_guard(intro)

        self.assertTrue(ok)
        self.assertEqual(guard["pcm_bytes"], 485376)
        self.assertEqual(guard["max_pcm_bytes"], 512000)

    def test_fast_demo_story_voice_starts_only_after_story_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            ignored = app.listen_fast_demo_story({"transcript": "小安你好", "send_to_robot": False})
            started = app.listen_fast_demo_story({"transcript": "小安讲故事", "send_to_robot": False})

        self.assertFalse(ignored["ok"])
        self.assertEqual(ignored["error"], "story_keyword_not_matched")
        self.assertTrue(started["ok"])
        self.assertEqual(started["action"], "story.voice_start")
        self.assertEqual(started["result"]["story"]["current_node"]["id"], "intro")

    def test_fast_demo_story_voice_command_is_asr_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            command = app.fast_demo_story_voice_command()

        self.assertIn("--decision-mode", command)
        self.assertIn("asr_only", command)
        self.assertNotIn("--local-demo-link", command)

    def test_fast_demo_story_and_dance_listen_are_blocked_while_work_voice_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.link_processes["work_voice"] = FakeRunningProcess()
            story = app.listen_fast_demo_story({"send_to_robot": False})
            dance = app.listen_fast_demo_dance({"send_to_robot": False})

        self.assertFalse(story["ok"])
        self.assertEqual(story["error"], "work_mode_running_use_stop_first")
        self.assertFalse(dance["ok"])
        self.assertEqual(dance["error"], "work_mode_running_use_stop_first")

    def test_fast_demo_story_voice_choice_advances_without_clicking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.listen_fast_demo_story({"transcript": "小安讲故事", "send_to_robot": False})
            chosen = app.listen_fast_demo_story({"transcript": "检查蓝色齿轮", "send_to_robot": False})

        self.assertTrue(chosen["ok"])
        self.assertEqual(chosen["action"], "story.voice_choice")
        self.assertEqual(chosen["result"]["choice"]["id"], "gear")
        self.assertEqual(chosen["result"]["story"]["current_node"]["id"], "gear")

    def test_fast_demo_story_voice_keyword_restarts_even_when_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            app.listen_fast_demo_story({"transcript": "小安讲故事", "send_to_robot": False})
            app.listen_fast_demo_story({"transcript": "检查蓝色齿轮", "send_to_robot": False})
            restarted = app.listen_fast_demo_story({"transcript": "重新讲故事", "send_to_robot": False})

        self.assertTrue(restarted["ok"])
        self.assertEqual(restarted["action"], "story.voice_start")
        self.assertEqual(restarted["result"]["story"]["current_node"]["id"], "intro")

    def test_fast_demo_dance_voice_keyword_sends_intro_then_sing_dance_command(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.listen_fast_demo_dance({
                "transcript": "小安，跳个舞",
                "send_to_robot": True,
                "allow_motion": True,
            })
            state = app.fast_demo_dance_state(robot={})

        self.assertTrue(result["ok"])
        self.assertTrue(result["keyword_matched"])
        self.assertEqual([payload["command"] for payload in sent], ["display.expression", "audio.play_tts", "demo.sing_dance"])
        self.assertEqual(sent[0]["expression"], "surprised")
        self.assertEqual(sent[1]["text"], DANCE_INTRO_TEXT)
        self.assertEqual(sent[1]["playback_mode"], "buffered")
        self.assertEqual(sent[2]["style"], "ode_to_joy")
        self.assertEqual(sent[2]["duration_ms"], 13000)
        self.assertEqual(state["asr_text"], "小安，跳个舞")
        self.assertTrue(state["keyword_matched"])

    def test_fast_demo_tts_texts_include_dance_intro(self) -> None:
        items = iter_fast_demo_tts_texts()

        self.assertTrue(any(
            item.get("link") == "dance" and item.get("intent") == "intro" and item.get("text") == DANCE_INTRO_TEXT
            for item in items
        ))

    def test_fast_demo_dance_voice_ignores_non_keyword_text(self) -> None:
        sent: list[dict] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(
                runtime_dir=temp_dir,
                command_sender=lambda payload: sent.append(payload) or {"ok": True, "ack": {"payload": {"ok": True}}},
            )
            result = app.listen_fast_demo_dance({
                "transcript": "小安你好",
                "send_to_robot": True,
                "allow_motion": True,
            })

        self.assertFalse(result["ok"])
        self.assertFalse(result["keyword_matched"])
        self.assertEqual(sent, [])

    def test_fast_demo_story_voice_start_moves_out_before_first_tts_when_allowed(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            app._wait_motion_completed = lambda steps, action_id, timeout_ms: steps.append({
                "name": "wait:motion.completed",
                "ok": True,
                "result": {"action_id": action_id},
            })
            result = app.listen_fast_demo_story({
                "transcript": "小安讲故事",
                "send_to_robot": True,
                "allow_motion": True,
            })

        self.assertTrue(result["ok"])
        self.assertEqual(
            [payload["command"] for payload in sent],
            ["motion.execute", "display.expression", "audio.play_tts"],
        )
        self.assertEqual(sent[0]["action"], "move_out_of_dock")

    def test_process_due_fast_demo_reminder_is_guarded_against_concurrent_polling(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            time.sleep(0.05)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            reminder_path = runtime / "integration_console" / "fast_demo" / "reminders.json"
            reminder_path.parent.mkdir(parents=True)
            reminder_path.write_text(
                json.dumps(
                    {
                        "schema_version": "xiaoan.fast_demo_reminders.v1",
                        "items": [
                            {
                                "id": "fast-reminder-concurrent",
                                "status": "pending",
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "due_at": datetime.now(timezone.utc).isoformat(),
                                "transcript": "小安，10秒后提醒我喝水",
                                "send_to_robot": True,
                                "allow_motion": True,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = IntegrationConsoleApp(runtime_dir=runtime, command_sender=sender)
            app._wait_motion_completed = lambda steps, action_id, timeout_ms: steps.append({
                "name": "wait:motion.completed",
                "ok": True,
                "result": {"action_id": action_id},
            })
            with patch("base_station.integration_console.console_server.POST_MOTION_TTS_SETTLE_SECONDS", 0.0):
                results: list[dict] = []
                threads = [
                    threading.Thread(target=lambda: results.append(app.process_due_fast_demo_reminders()))
                    for _ in range(2)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
            saved = json.loads(reminder_path.read_text(encoding="utf-8"))

        self.assertEqual(sum(result["processed"] for result in results), 1)
        self.assertEqual(saved["items"][0]["status"], "fired")
        self.assertEqual(
            [payload["command"] for payload in sent],
            ["display.expression", "motion.execute", "audio.play_tts"],
        )

    def test_robot_expression_payload_is_agent_command(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.send_expression({"expression": "happy", "duration_ms": 1500, "loop": False})

        self.assertTrue(result["ok"])
        self.assertEqual(sent[0]["command"], "display.expression")
        self.assertEqual(sent[0]["expression"], "happy")
        self.assertEqual(sent[0]["duration_ms"], 1500)

    def test_robot_tts_payload_uses_generated_pcm_duration(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.send_tts({"text": "你好，我是小安。", "duration_ms": 3000})

        self.assertTrue(result["ok"])
        self.assertEqual(sent[0]["command"], "audio.play_tts")
        self.assertEqual(sent[0]["text"], "你好，我是小安。")
        self.assertNotIn("duration_ms", sent[0])

    def test_motion_payload_uses_safe_defaults_and_action_id(self) -> None:
        sent: list[dict] = []

        def sender(payload: dict) -> dict:
            sent.append(payload)
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.send_motion({
                "action": "move_out_of_dock",
                "params": {"speed": 0.9, "distance_cm": 99, "timeout_ms": 9999},
                "bench": False,
            })

        self.assertTrue(result["ok"])
        payload = sent[0]
        self.assertEqual(payload["command"], "motion.execute")
        self.assertEqual(payload["action"], "move_out_of_dock")
        self.assertEqual(payload["params"]["speed"], 0.9)
        self.assertEqual(payload["params"]["distance_cm"], 10.0)
        self.assertEqual(payload["timeout_ms"], 1200)
        self.assertTrue(payload["action_id"].startswith("console-"))

    def test_scenario_runs_steps_in_order(self) -> None:
        sent: list[str] = []

        def sender(payload: dict) -> dict:
            sent.append(payload["command"])
            return {"ok": True, "ack": {"type": "agent.ack", "payload": {"ok": True}}}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir, command_sender=sender)
            result = app.run_scenario({"scenario": "direct-smoke"})

        self.assertTrue(result["ok"])
        self.assertEqual(sent, ["display.expression", "display.expression", "audio.play_local"])
        self.assertEqual(
            [step["name"] for step in result["steps"]],
            ["expression:idle", "expression:happy", "local_sound:success_ding"],
        )

    def test_tool_runner_rejects_arbitrary_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            result = app.run_tool({"tool": "echo hacked && rm -rf /"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "tool_not_allowed")


class IntegrationConsoleStateReaderTest(unittest.TestCase):
    def test_read_ws_state_handles_missing_empty_and_bad_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            missing = read_ws_state(runtime)
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["reason"], "not_found")

            (runtime / "ws_state.json").write_text("", encoding="utf-8")
            empty = read_ws_state(runtime)
            self.assertFalse(empty["ok"])
            self.assertEqual(empty["reason"], "empty")

            (runtime / "ws_state.json").write_text("{bad", encoding="utf-8")
            bad = read_ws_state(runtime)
            self.assertFalse(bad["ok"])
            self.assertTrue(bad["reason"].startswith("bad_json"))

    def test_visual_state_handles_missing_corrupt_and_stale_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = IntegrationConsoleApp(runtime_dir=temp_dir)
            missing = app.visual_state()
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["reason"], "not_found")

            visual_dir = Path(temp_dir) / "integration_console" / "visual"
            visual_dir.mkdir(parents=True)
            state_path = visual_dir / "latest_state.json"
            state_path.write_text("{bad", encoding="utf-8")
            corrupt = app.visual_state()
            self.assertFalse(corrupt["ok"])
            self.assertTrue(corrupt["reason"].startswith("bad_json"))

            state_path.write_text(
                json.dumps({"schema_version": "visual_console_v1", "snapshot_id": "old"}),
                encoding="utf-8",
            )
            old = time.time() - 5
            os.utime(state_path, (old, old))
            stale = app.visual_state()

        self.assertTrue(stale["ok"])
        self.assertEqual(stale["freshness"], "stale")
        self.assertGreaterEqual(stale["age_ms"], 4900)


if __name__ == "__main__":
    unittest.main()
