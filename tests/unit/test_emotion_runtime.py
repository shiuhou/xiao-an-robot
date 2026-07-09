"""Unit tests for emotion_runtime model backend selection."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
from pathlib import Path
import unittest
from unittest.mock import patch

from base_station.monitor.emotion_runtime import (
    BaseStationEmotionRuntime,
    VLMGatedCameraEmotionSource,
    create_runtime,
    create_emotion_source,
    create_face_emotion_model,
    create_vlm_emotion_model,
    fuse_cv_vlm_sample,
    main,
    parse_args,
)
from base_station.perception.openvino_qwen_vl_emotion_model import OpenVINOQwenVLEmotionModel
from base_station.perception.qwen_vl_emotion_model import FakeQwenVLEmotionModel


def write_test_png(path: Path) -> None:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:
        raise unittest.SkipTest(f"OpenCV/numpy not available for image fixture: {exc}") from exc

    image = np.zeros((1, 1, 3), dtype=np.uint8)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"failed to write test image: {path}")


class FakeEventLoop:
    def __init__(self) -> None:
        self.samples = []

    async def handle_sample(self, sample: dict) -> dict:
        self.samples.append(sample)
        should_handle = sample["fatigue_score"] >= 0.7 or sample["emotion_tag"] in {"sad", "anxious", "tired"}
        return {
            "handled": should_handle,
            "reason": "care" if should_handle else "normal",
            "message": sample["emotion_tag"],
        }


class FakeOpenCVCameraFrameSource:
    def __init__(
        self,
        camera_index: int = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.closed = False

    async def frames(self):
        try:
            yield {
                "source": "opencv_camera",
                "frame_id": 1,
                "timestamp_ms": 456,
                "width": self.width or 640,
                "height": self.height or 480,
                "payload": "frame",
            }
        finally:
            self.closed = True

    def close(self) -> None:
        self.closed = True


class FakeWebSocketVideoFrameSource:
    def __init__(self, maxsize: int = 2) -> None:
        self.maxsize = maxsize

    async def frames(self):
        if False:
            yield {}


class FakeWebSocketVideoObserverSource:
    def __init__(self, url: str, reconnect_delay_seconds: float = 1.0) -> None:
        self.url = url
        self.reconnect_delay_seconds = reconnect_delay_seconds

    async def frames(self):
        if False:
            yield {}


class FakeVisualTracePublisher:
    def __init__(self, output_dir: str, max_fps: float = 1.0) -> None:
        self.output_dir = output_dir
        self.max_fps = max_fps


class FakeRuntimeSource:
    def __init__(self) -> None:
        self.frame_source = object()


class FakeRuntime:
    def __init__(self) -> None:
        self.source = FakeRuntimeSource()
        self.event_loop = type("EventLoop", (), {"brain": None})()
        self.ran = False

    async def run(self) -> list[dict]:
        self.ran = True
        return []


class FakeWebSocketServer:
    def __init__(self) -> None:
        self.closed = False
        self.waited = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited = True


class FakeWsServerModule:
    def __init__(self) -> None:
        self.video_sources = []
        self.start_calls = []
        self.server = FakeWebSocketServer()

    def set_video_frame_source(self, source) -> None:
        self.video_sources.append(source)

    async def start_server(self, host: str, port: int):
        self.start_calls.append((host, port))
        return self.server

    async def heartbeat_monitor(self):
        while True:
            await asyncio.sleep(3600)


class EmotionRuntimeBackendTest(unittest.IsolatedAsyncioTestCase):
    async def test_ws_video_visual_trace_args_are_available(self) -> None:
        args = parse_args([
            "--source",
            "ws_video",
            "--listen-host",
            "0.0.0.0",
            "--video-queue-size",
            "4",
            "--enable-vlm-gate",
            "--visual-trace-dir",
            "runtime/integration_console/visual",
            "--visual-trace-fps",
            "1.5",
        ])

        self.assertEqual(args.source, "ws_video")
        self.assertEqual(args.listen_host, "0.0.0.0")
        self.assertEqual(args.video_queue_size, 4)
        self.assertEqual(args.visual_trace_dir, "runtime/integration_console/visual")
        self.assertEqual(args.visual_trace_fps, 1.5)
        self.assertFalse(args.no_visual_trace)

    async def test_visual_trace_fps_accepts_fast_console_rate(self) -> None:
        args = parse_args(["--source", "ws_video", "--visual-trace-fps", "5.0"])
        self.assertEqual(args.visual_trace_fps, 5.0)

    async def test_visual_trace_fps_is_bounded(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["--source", "ws_video", "--visual-trace-fps", "10.1"])

    async def test_ws_video_source_uses_websocket_frame_source_and_visual_observer(self) -> None:
        observer = object()
        with patch(
            "base_station.monitor.emotion_runtime._load_ws_video_frame_source",
            return_value=FakeWebSocketVideoFrameSource,
        ):
            source = create_emotion_source(
                source="ws_video",
                pattern="tired",
                count=None,
                interval_seconds=0,
                model_backend="mock",
                enable_vlm_gate=True,
                vlm_backend="fake",
                visual_observer=observer,
                video_queue_size=4,
            )

        self.assertIsInstance(source, VLMGatedCameraEmotionSource)
        self.assertIsInstance(source.frame_source, FakeWebSocketVideoFrameSource)
        self.assertEqual(source.frame_source.maxsize, 4)
        self.assertIs(source.visual_observer, observer)

    async def test_ws_video_observer_source_uses_configured_host_port(self) -> None:
        observer = object()
        with patch(
            "base_station.monitor.emotion_runtime._load_ws_video_observer_source",
            return_value=FakeWebSocketVideoObserverSource,
        ):
            source = create_emotion_source(
                source="ws_video_observer",
                pattern="tired",
                count=None,
                interval_seconds=0,
                host="192.168.1.20",
                port=9876,
                model_backend="mock",
                enable_vlm_gate=True,
                vlm_backend="fake",
                visual_observer=observer,
            )

        self.assertIsInstance(source, VLMGatedCameraEmotionSource)
        self.assertIsInstance(source.frame_source, FakeWebSocketVideoObserverSource)
        self.assertEqual(source.frame_source.url, "ws://192.168.1.20:9876/video-observer")
        self.assertIs(source.visual_observer, observer)

    async def test_ws_video_source_requires_vlm_gate(self) -> None:
        with self.assertRaisesRegex(ValueError, "--enable-vlm-gate is required"):
            create_emotion_source(
                source="ws_video",
                pattern="tired",
                count=None,
                interval_seconds=0,
                model_backend="mock",
                enable_vlm_gate=False,
            )

    async def test_create_runtime_builds_visual_trace_observer_for_gated_source(self) -> None:
        with (
            patch(
                "base_station.monitor.emotion_runtime._load_ws_video_frame_source",
                return_value=FakeWebSocketVideoFrameSource,
            ),
            patch(
                "base_station.monitor.emotion_runtime._load_visual_trace_publisher",
                return_value=FakeVisualTracePublisher,
            ),
        ):
            runtime = create_runtime(
                source_name="ws_video",
                pattern="tired",
                count=None,
                interval_seconds=0,
                model_backend="mock",
                enable_vlm_gate=True,
                vlm_backend="fake",
                visual_trace_dir="runtime/integration_console/visual",
                visual_trace_fps=1.25,
                video_queue_size=3,
                no_agent=True,
            )

        observer = runtime.source.visual_observer
        self.assertIsInstance(observer, FakeVisualTracePublisher)
        self.assertEqual(observer.output_dir, "runtime/integration_console/visual")
        self.assertEqual(observer.max_fps, 1.25)

    async def test_main_ws_video_starts_server_with_runtime_frame_source_and_cleans_up(self) -> None:
        args = parse_args([
            "--source",
            "ws_video",
            "--listen-host",
            "127.0.0.1",
            "--port",
            "9876",
            "--enable-vlm-gate",
            "--no-agent",
        ])
        fake_runtime = FakeRuntime()
        fake_ws_server = FakeWsServerModule()

        with (
            patch("base_station.monitor.emotion_runtime.create_runtime", return_value=fake_runtime),
            patch("base_station.monitor.emotion_runtime._load_ws_server", return_value=fake_ws_server),
        ):
            await main(args)

        self.assertTrue(fake_runtime.ran)
        self.assertEqual(fake_ws_server.start_calls, [("127.0.0.1", 9876)])
        self.assertEqual(
            fake_ws_server.video_sources,
            [fake_runtime.source.frame_source, None],
        )
        self.assertTrue(fake_ws_server.server.closed)
        self.assertTrue(fake_ws_server.server.waited)

    async def test_vlm_gate_args_are_available(self) -> None:
        args = parse_args([
            "--enable-vlm-gate",
            "--vlm-backend",
            "openvino_qwen_vl",
            "--vlm-model-path",
            "models/qwen-vl-openvino",
            "--vlm-max-new-tokens",
            "48",
            "--force-vlm",
        ])

        self.assertTrue(args.enable_vlm_gate)
        self.assertEqual(args.vlm_backend, "openvino_qwen_vl")
        self.assertEqual(args.vlm_model_path, "models/qwen-vl-openvino")
        self.assertEqual(args.vlm_max_new_tokens, 48)
        self.assertTrue(args.force_vlm)

    async def test_vlm_gate_disabled_keeps_default_camera_flow(self) -> None:
        source = create_emotion_source(
            source="fake_camera",
            pattern="neutral",
            count=1,
            interval_seconds=0,
            model_backend="mock",
        )
        event_loop = FakeEventLoop()
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        await runtime.run()

        sample = event_loop.samples[0]
        self.assertEqual(sample["source"], "fake_face")
        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertNotIn("vlm_triggered", sample)

    async def test_vlm_gate_neutral_does_not_trigger_vlm(self) -> None:
        source = create_emotion_source(
            source="fake_camera",
            pattern="neutral",
            count=1,
            interval_seconds=0,
            model_backend="mock",
            enable_vlm_gate=True,
        )
        event_loop = FakeEventLoop()
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        results = await runtime.run()

        self.assertEqual(results, [])
        self.assertEqual(event_loop.samples, [])
    async def test_vlm_gate_tired_triggers_qwen_vl(self) -> None:
        source = create_emotion_source(
            source="fake_camera",
            pattern="tired",
            count=1,
            interval_seconds=0,
            model_backend="mock",
            enable_vlm_gate=True,
            vlm_backend="qwen_vl",
        )
        event_loop = FakeEventLoop()
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        await runtime.run()

        sample = event_loop.samples[0]
        self.assertEqual(sample["source"], "fake_face")
        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertEqual(sample["vlm_triggered"], True)
        self.assertEqual(sample["vlm_trigger_reason"], "negative_emotion")
        self.assertEqual(sample["vlm"]["executed"], True)
        self.assertEqual(sample["vlm"]["status"], "ok")
        self.assertEqual(sample["vlm"]["expression_label"], "tired")
        self.assertEqual(sample["vlm"]["confidence"], 0.9)
        self.assertEqual(sample["vlm"]["evidence"], [])
        self.assertEqual(sample["vlm"]["face_observation"], "The user may need a short rest.")
        self.assertEqual(sample["cv_sample"]["source"], "fake_face")
    async def test_force_vlm_triggers_qwen_vl_for_neutral_sample(self) -> None:
        source = create_emotion_source(
            source="fake_camera",
            pattern="neutral",
            count=1,
            interval_seconds=0,
            model_backend="mock",
            enable_vlm_gate=True,
            force_vlm=True,
        )
        event_loop = FakeEventLoop()
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        await runtime.run()

        sample = event_loop.samples[0]
        self.assertEqual(sample["source"], "fake_face")
        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["vlm_triggered"], True)
        self.assertEqual(sample["vlm_trigger_reason"], "force")
        self.assertEqual(sample["vlm"]["executed"], True)
        self.assertEqual(sample["vlm"]["status"], "ok")
        self.assertEqual(sample["vlm"]["expression_label"], "neutral")
    async def test_openvino_qwen_vl_vlm_backend_requires_vlm_model_path(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "--vlm-model-path is required when --vlm-backend openvino_qwen_vl",
        ):
            create_emotion_source(
                source="fake_camera",
                pattern="tired",
                count=1,
                interval_seconds=0,
                model_backend="mock",
                enable_vlm_gate=True,
                vlm_backend="openvino_qwen_vl",
            )

    async def test_openvino_qwen_vl_vlm_backend_creates_wrapper(self) -> None:
        model = create_vlm_emotion_model(
            vlm_backend="openvino_qwen_vl",
            pattern="neutral",
            vlm_model_path="models/qwen-vl-openvino",
            device="GPU",
            vlm_max_new_tokens=48,
        )

        self.assertIsInstance(model, OpenVINOQwenVLEmotionModel)
        self.assertEqual(model.runner.model_dir, "models/qwen-vl-openvino")
        self.assertEqual(model.runner.device, "GPU")
        self.assertEqual(model.runner.max_new_tokens, 48)

    async def test_openvino_qwen_vl_is_legal_model_backend_arg(self) -> None:
        args = parse_args(["--model-backend", "openvino_qwen_vl"])

        self.assertEqual(args.model_backend, "openvino_qwen_vl")

    async def test_image_file_source_arg_requires_image_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "--image-path is required"):
            create_emotion_source(
                source="image_file",
                pattern="neutral",
                count=1,
                interval_seconds=0,
                model_backend="qwen_vl",
            )

    async def test_image_file_source_with_qwen_vl_fake_backend_outputs_frame_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.png"
            write_test_png(image_path)
            source = create_emotion_source(
                source="image_file",
                image_path=str(image_path),
                pattern="tired",
                count=1,
                interval_seconds=0,
                model_backend="qwen_vl",
            )

            event_loop = FakeEventLoop()
            runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)
            await runtime.run()

        sample = event_loop.samples[0]
        self.assertEqual(sample["source"], "fake_qwen_vl")
        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertEqual(sample["frame_source"], "image_file")
        self.assertEqual(sample["frame_id"], 1)
        self.assertEqual(sample["width"], 1)
        self.assertEqual(sample["height"], 1)

    async def test_image_file_vlm_gate_with_qwen_vl_fake_backend_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.png"
            write_test_png(image_path)
            source = create_emotion_source(
                source="image_file",
                image_path=str(image_path),
                pattern="tired",
                count=1,
                interval_seconds=0,
                model_backend="mock",
                enable_vlm_gate=True,
                vlm_backend="qwen_vl",
            )

            event_loop = FakeEventLoop()
            runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)
            await runtime.run()

        sample = event_loop.samples[0]
        self.assertEqual(sample["frame_source"], "image_file")
        self.assertEqual(sample["vlm_triggered"], True)
        self.assertEqual(sample["vlm"]["expression_label"], "tired")

    async def test_model_root_alias_maps_to_model_path(self) -> None:
        args = parse_args(["--model-backend", "openvino", "--model-root", "models/face.xml"])

        self.assertEqual(args.model_path, "models/face.xml")

    async def test_vlm_model_root_alias_maps_to_vlm_model_path(self) -> None:
        args = parse_args(["--enable-vlm-gate", "--vlm-model-root", "models/qwen-vl-openvino"])

        self.assertEqual(args.vlm_model_path, "models/qwen-vl-openvino")

    async def test_openvino_missing_model_path_does_not_import_openvino(self) -> None:
        with patch("base_station.monitor.emotion_runtime.OpenVINOFaceEmotionModel", None):
            with patch.dict(sys.modules, {"openvino": None, "openvino.runtime": None}):
                with self.assertRaisesRegex(
                    FileNotFoundError,
                    "OpenVINO CV model",
                ):
                    create_face_emotion_model(
                        model_backend="openvino",
                        pattern="neutral",
                    )

    async def test_fake_vlm_backend_creates_fake_qwen_model(self) -> None:
        model = create_vlm_emotion_model(vlm_backend="fake", pattern="neutral")

        self.assertIsInstance(model, FakeQwenVLEmotionModel)

    async def test_qwen_vl_vlm_backend_remains_fake_alias(self) -> None:
        model = create_vlm_emotion_model(vlm_backend="qwen_vl", pattern="neutral")

        self.assertIsInstance(model, FakeQwenVLEmotionModel)

    async def test_vlm_face_backend_missing_model_path_reports_clear_error(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "VLM model not found"):
            create_vlm_emotion_model(vlm_backend="vlm_face", pattern="neutral", vlm_model_path="missing-vlm")

    async def test_openvino_qwen_vl_requires_model_path(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "--model-path is required when --model-backend openvino_qwen_vl",
        ):
            create_face_emotion_model(
                model_backend="openvino_qwen_vl",
                pattern="neutral",
            )

    async def test_openvino_qwen_vl_backend_creates_wrapper_with_runner_config(self) -> None:
        model = create_face_emotion_model(
            model_backend="openvino_qwen_vl",
            pattern="neutral",
            model_path="models/qwen-vl-openvino",
            device="GPU",
        )

        self.assertIsInstance(model, OpenVINOQwenVLEmotionModel)
        self.assertEqual(model.runner.model_dir, "models/qwen-vl-openvino")
        self.assertEqual(model.runner.device, "GPU")

    async def test_openvino_qwen_vl_camera_source_uses_direct_model_pipeline(self) -> None:
        source = create_emotion_source(
            source="fake_camera",
            pattern="neutral",
            count=1,
            interval_seconds=0,
            model_backend="openvino_qwen_vl",
            model_path="models/qwen-vl-openvino",
            device="NPU",
        )

        self.assertIsInstance(source.pipeline.model, OpenVINOQwenVLEmotionModel)
        self.assertEqual(source.pipeline.model.runner.model_dir, "models/qwen-vl-openvino")
        self.assertEqual(source.pipeline.model.runner.device, "NPU")

    async def test_qwen_vl_backend_creates_fake_qwen_model(self) -> None:
        model = create_face_emotion_model(model_backend="qwen_vl", pattern="neutral")

        self.assertIsInstance(model, FakeQwenVLEmotionModel)

    async def test_qwen_vl_fake_camera_neutral_outputs_fake_qwen_source_without_care(self) -> None:
        source = create_emotion_source(
            source="fake_camera",
            pattern="neutral",
            count=1,
            interval_seconds=0,
            model_backend="qwen_vl",
        )
        event_loop = FakeEventLoop()
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        results = await runtime.run()

        self.assertEqual(results[0]["handled"], False)
        self.assertEqual(results[0]["reason"], "normal")
        sample = event_loop.samples[0]
        self.assertEqual(sample["source"], "fake_qwen_vl")
        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["frame_source"], "fake_camera")

    async def test_qwen_vl_fake_camera_tired_outputs_vlm_fields_and_triggers_care(self) -> None:
        source = create_emotion_source(
            source="fake_camera",
            pattern="tired",
            count=1,
            interval_seconds=0,
            model_backend="qwen_vl",
        )
        event_loop = FakeEventLoop()
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        results = await runtime.run()

        self.assertEqual(results[0]["handled"], True)
        sample = event_loop.samples[0]
        self.assertEqual(sample["source"], "fake_qwen_vl")
        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertGreaterEqual(sample["fatigue_score"], 0.7)
        self.assertIn("visual_reason", sample)
        self.assertIn("vlm_observation", sample)

    async def test_qwen_vl_opencv_camera_source_outputs_frame_metadata(self) -> None:
        with patch(
            "base_station.monitor.emotion_runtime.OpenCVCameraFrameSource",
            FakeOpenCVCameraFrameSource,
        ):
            source = create_emotion_source(
                source="opencv_camera",
                pattern="anxious",
                count=1,
                interval_seconds=0,
                model_backend="qwen_vl",
            )
        event_loop = FakeEventLoop()
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        await runtime.run()

        sample = event_loop.samples[0]
        self.assertEqual(sample["source"], "fake_qwen_vl")
        self.assertEqual(sample["emotion_tag"], "anxious")
        self.assertEqual(sample["frame_source"], "opencv_camera")
        self.assertEqual(sample["frame_id"], 1)
        self.assertEqual(sample["timestamp_ms"], 456)

    async def test_unsupported_backend_still_reports_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported model backend"):
            create_face_emotion_model(model_backend="unknown", pattern="neutral")


class _OneFrameSource:
    def __init__(self, frame):
        self._frame = frame

    async def frames(self):
        yield self._frame


class _TwoFrameSource:
    async def frames(self):
        yield {"frame_id": 1, "timestamp_ms": 100, "payload": None}
        await asyncio.sleep(0)
        yield {"frame_id": 2, "timestamp_ms": 200, "payload": None}


class _FixedCvPipeline:
    def __init__(self, cv_sample, observation=None):
        self._cv = cv_sample
        self.last_observation = observation if observation is not None else {"face_confidence": 0.9}

    def process_frame(self, frame):
        return dict(self._cv)


class _AlwaysTriggerGate:
    def __init__(self):
        self.evaluate_calls = 0

    def evaluate(self, cv_sample, force_vlm=False):
        self.evaluate_calls += 1
        return {"should_trigger": True, "reason": "test"}

    def diagnostics(self, cv_sample, result):
        return {"result": dict(result), "fatigue": {"value": cv_sample.get("fatigue_score")}}


class _RecordingObserver:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def _record(self, name, payload):
        self.calls.append((name, payload))
        if self.fail:
            raise RuntimeError(f"observer {name} failed")

    def observe_frame(self, **payload):
        self._record("observe_frame", payload)
        return {"snapshot_id": "frame-1", "frame_id": 1, "request_id": "vlm-1"}

    def vlm_started(self, token, reason):
        self._record("vlm_started", {"token": token, "reason": reason})
        return token["request_id"]

    def vlm_finished(self, request_id, **payload):
        self._record("vlm_finished", {"request_id": request_id, **payload})


class _FixedContextBuilder:
    def build(self, **kwargs):
        return {}


class _FixedVlm:
    def __init__(self, prediction):
        self._prediction = prediction
        self.last_frame = None

    def predict(self, frame, context=None):
        self.last_frame = frame
        return dict(self._prediction)


class _FailingVlm:
    def predict(self, frame, context=None):
        raise RuntimeError("generation failed with a long stack that should not escape")


class _BlockingVlm:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def predict(self, frame, context=None):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=2)
        return {"expression_label": "tired"}


class FusionPolicyTest(unittest.TestCase):
    def test_cv_tired_and_vlm_tired_agree_negative(self):
        sample = fuse_cv_vlm_sample(
            {"source": "cv", "emotion_tag": "tired", "confidence": 0.7, "fatigue_score": 0.8},
            {"executed": True, "status": "ok", "emotion_tag": "tired", "confidence": 0.9, "fatigue_score": 0.85},
        )

        self.assertEqual(sample["fusion"]["decision"], "cv_vlm_agree_negative")
        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertEqual(sample["confidence"], 0.7)
        self.assertEqual(sample["fatigue_score"], 0.8)

    def test_neutral_cv_high_confidence_vlm_tired_is_promoted(self):
        sample = fuse_cv_vlm_sample(
            {"source": "cv", "emotion_tag": "neutral", "confidence": 0.6, "fatigue_score": 0.2},
            {"executed": True, "status": "ok", "emotion_tag": "tired", "confidence": 0.8, "fatigue_score": 0.75},
        )

        self.assertEqual(sample["fusion"]["decision"], "vlm_negative_aux_only")
        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["confidence"], 0.6)
        self.assertEqual(sample["fatigue_score"], 0.2)

    def test_low_confidence_cv_tired_high_confidence_vlm_neutral_is_suppressed(self):
        sample = fuse_cv_vlm_sample(
            {"source": "cv", "emotion_tag": "tired", "confidence": 0.5, "fatigue_score": 0.6},
            {"executed": True, "status": "ok", "emotion_tag": "neutral", "confidence": 0.9, "fatigue_score": 0.1},
        )

        self.assertEqual(sample["fusion"]["decision"], "vlm_neutral_aux_only")
        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertEqual(sample["confidence"], 0.5)
        self.assertEqual(sample["fatigue_score"], 0.6)

    def test_high_confidence_cv_tired_is_not_suppressed_by_neutral_vlm(self):
        sample = fuse_cv_vlm_sample(
            {"source": "cv", "emotion_tag": "tired", "confidence": 0.8, "fatigue_score": 0.8},
            {"executed": True, "status": "ok", "emotion_tag": "neutral", "confidence": 0.95, "fatigue_score": 0.1},
        )

        self.assertEqual(sample["fusion"]["decision"], "vlm_neutral_aux_only")
        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertEqual(sample["fatigue_score"], 0.8)

    def test_vlm_error_keeps_cv_only(self):
        sample = fuse_cv_vlm_sample(
            {"source": "cv", "emotion_tag": "tired", "confidence": 0.7, "fatigue_score": 0.8},
            {"executed": False, "status": "error", "error": "JSON parse failed"},
        )

        self.assertEqual(sample["fusion"]["decision"], "cv_only_vlm_error")
        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertEqual(sample["vlm"]["error"], "JSON parse failed")

    def test_auxiliary_vlm_keeps_cv_primary(self):
        sample = fuse_cv_vlm_sample(
            {"source": "cv", "emotion_tag": "neutral", "confidence": 0.7, "fatigue_score": 0.2},
            {"executed": True, "status": "ok", "emotion_tag": "happy", "confidence": 0.8, "fatigue_score": 0.0},
        )

        self.assertEqual(sample["fusion"]["decision"], "cv_primary_vlm_aux")
        self.assertEqual(sample["emotion_tag"], "neutral")


class VLMGatedAssemblyTest(unittest.IsolatedAsyncioTestCase):
    async def _run_one(self, cv_sample, prediction):
        source = VLMGatedCameraEmotionSource(
            frame_source=_OneFrameSource({"payload": None}),
            cv_pipeline=_FixedCvPipeline(cv_sample),
            gate=_AlwaysTriggerGate(),
            context_builder=_FixedContextBuilder(),
            vlm_model=_FixedVlm(prediction),
        )
        return [sample async for sample in source.samples()][0]

    async def test_triggered_frame_normalizes_scale_and_derives_polarity(self):
        cv_sample = {
            "source": "openface",
            "emotion_tag": "neutral",
            "confidence": 0.5,
            "fatigue_score": 42.0,
            "polarity": "positive",
            "fatigue_level": "medium",
            "valence": "neutral",
            "observation_quality": 0.99,
            "presence_state": "present",
            "evidence_codes": ["PERCLOS_HIGH"],
            "au_json": {"AU01": 0.1},
        }
        prediction = {
            "source": "openvino_qwen_vl",
            "emotion_tag": "tired",
            "confidence": 0.9,
            "fatigue_score": 0.8,
            "visual_reason": "eyes heavy",
            "vlm_observation": "needs rest",
        }
        sample = await self._run_one(cv_sample, prediction)

        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertTrue(sample["vlm_triggered"])
        self.assertEqual(sample["vlm_trigger_reason"], "test")
        self.assertEqual(sample["vlm"], {
            "executed": True,
            "status": "ok",
            "expression_label": "tired",
            "emotion_tag": "tired",
            "emotion_score": None,
            "confidence": 0.9,
            "fatigue_score": 0.8,
            "visual_reason": "eyes heavy",
            "vlm_observation": "needs rest",
            "evidence": [],
            "face_observation": "needs rest",
            "message": "",
            "valid_observation": None,
        })
        self.assertEqual(sample["fusion"]["decision"], "vlm_negative_aux_only")
        self.assertEqual(sample["fatigue_score"], 42.0)
        self.assertEqual(sample["polarity"], "positive")
        self.assertEqual(sample["fatigue_level"], "medium")
        self.assertEqual(sample["observation_quality"], 0.99)
        self.assertEqual(sample["presence_state"], "present")
        self.assertEqual(sample["evidence_codes"], ["PERCLOS_HIGH"])
        self.assertEqual(sample["au_json"], {"AU01": 0.1})
        self.assertEqual(sample["cv_sample"]["fatigue_score"], 42.0)
    async def test_triggered_missing_vlm_fields_get_safe_defaults(self):
        sample = await self._run_one(
            {"source": "openface", "emotion_tag": "neutral", "fatigue_score": 10.0},
            {"expression_label": "neutral"},
        )
        self.assertEqual(sample["vlm"], {
            "executed": True,
            "status": "ok",
            "expression_label": "neutral",
            "emotion_tag": "neutral",
            "emotion_score": None,
            "confidence": None,
            "fatigue_score": None,
            "visual_reason": "",
            "vlm_observation": "",
            "evidence": [],
            "face_observation": "",
            "message": "",
            "valid_observation": None,
        })

    async def test_payload_free_frame_gets_synthetic_payload_for_vlm(self):
        vlm = _FixedVlm({"expression_label": "neutral"})
        source = VLMGatedCameraEmotionSource(
            frame_source=_OneFrameSource({"source": "fake_camera", "width": 64, "height": 48, "payload": None}),
            cv_pipeline=_FixedCvPipeline({"source": "fake_face", "emotion_tag": "tired", "fatigue_score": 0.85}),
            gate=_AlwaysTriggerGate(),
            context_builder=_FixedContextBuilder(),
            vlm_model=vlm,
        )

        sample = [item async for item in source.samples()][0]

        self.assertEqual(sample["source"], "fake_face")
        self.assertIsNotNone(vlm.last_frame["payload"])

    async def test_triggered_negative_vlm_is_nested_and_does_not_override_cv(self):
        sample = await self._run_one(
            {"source": "openface", "emotion_tag": "neutral", "fatigue_score": 10.0},
            {
                "emotion_tag": "irritable",
                "polarity": "负面",
                "fatigue_score": 0.2,
            },
        )

        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["fatigue_score"], 10.0)
        self.assertNotIn("polarity", sample)
        self.assertEqual(sample["vlm"]["expression_label"], "irritable")
        self.assertTrue(sample["vlm"]["executed"])
        self.assertEqual(sample["fusion"]["decision"], "cv_primary_vlm_aux")

    async def test_triggered_positive_vlm_is_nested_and_does_not_override_cv(self):
        sample = await self._run_one(
            {"source": "openface", "emotion_tag": "stressed", "fatigue_score": 10.0},
            {
                "emotion_tag": "neutral",
                "polarity": "正面",
                "fatigue_score": 0.1,
            },
        )

        self.assertEqual(sample["emotion_tag"], "stressed")
        self.assertEqual(sample["fatigue_score"], 10.0)
        self.assertNotIn("polarity", sample)
        self.assertEqual(sample["vlm"]["expression_label"], "neutral")
        self.assertTrue(sample["vlm"]["executed"])
        self.assertEqual(sample["fusion"]["decision"], "cv_primary_vlm_aux")

    async def test_triggered_unknown_vlm_tag_is_nested_and_does_not_override_cv(self):
        sample = await self._run_one(
            {"source": "openface", "emotion_tag": "neutral", "fatigue_score": 10.0},
            {
                "emotion_tag": "overwhelmed",
                "polarity": "负面",
                "fatigue_score": 0.2,
            },
        )

        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertEqual(sample["fatigue_score"], 10.0)
        self.assertNotIn("polarity", sample)
        self.assertEqual(sample["vlm"]["expression_label"], "overwhelmed")
        self.assertTrue(sample["vlm"]["executed"])
        self.assertEqual(sample["fusion"]["decision"], "cv_primary_vlm_aux")

    async def test_vlm_exception_yields_cv_sample_with_error_fallback(self):
        source = VLMGatedCameraEmotionSource(
            frame_source=_OneFrameSource({"source": "fake_camera", "width": 64, "height": 48, "payload": None}),
            cv_pipeline=_FixedCvPipeline({
                "source": "fake_face",
                "emotion_tag": "tired",
                "confidence": 0.8,
                "fatigue_score": 0.85,
            }),
            gate=_AlwaysTriggerGate(),
            context_builder=_FixedContextBuilder(),
            vlm_model=_FailingVlm(),
        )

        sample = [item async for item in source.samples()][0]

        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertTrue(sample["vlm_triggered"])
        self.assertFalse(sample["vlm"]["executed"])
        self.assertEqual(sample["vlm"]["status"], "error")
        self.assertIn("generation failed", sample["vlm"]["error"])
        self.assertEqual(sample["fusion"]["decision"], "cv_only_vlm_error")

    async def test_visual_observer_receives_single_gate_evaluation_lifecycle(self):
        gate = _AlwaysTriggerGate()
        observer = _RecordingObserver()
        source = VLMGatedCameraEmotionSource(
            frame_source=_OneFrameSource({"frame_id": 1, "timestamp_ms": 123, "payload": None}),
            cv_pipeline=_FixedCvPipeline({
                "frame_id": 1,
                "timestamp_ms": 123,
                "emotion_tag": "tired",
                "confidence": 0.8,
                "fatigue_score": 80.0,
            }),
            gate=gate,
            context_builder=_FixedContextBuilder(),
            vlm_model=_FixedVlm({"expression_label": "tired"}),
            visual_observer=observer,
        )

        samples = [item async for item in source.samples()]

        self.assertEqual(len(samples), 1)
        self.assertEqual(gate.evaluate_calls, 1)
        self.assertEqual(
            [name for name, _payload in observer.calls],
            ["observe_frame", "vlm_started", "vlm_finished"],
        )
        observed = observer.calls[0][1]
        self.assertIs(observed["observation"], source.cv_pipeline.last_observation)
        self.assertEqual(observed["gate_diagnostics"]["result"]["reason"], "test")
        finished = observer.calls[-1][1]
        self.assertEqual(finished["request_id"], "vlm-1")
        self.assertEqual(finished["status"], "done")
        self.assertGreaterEqual(finished["latency_ms"], 0.0)

    async def test_no_face_observation_suppresses_vlm_trigger(self):
        gate = _AlwaysTriggerGate()
        observer = _RecordingObserver()
        vlm = _FixedVlm({"expression_label": "tired"})
        source = VLMGatedCameraEmotionSource(
            frame_source=_OneFrameSource({"frame_id": 1, "timestamp_ms": 123, "payload": None}),
            cv_pipeline=_FixedCvPipeline(
                {
                    "frame_id": 1,
                    "timestamp_ms": 123,
                    "emotion_tag": "tired",
                    "confidence": 0.9,
                    "fatigue_score": 100.0,
                },
                observation={"face_detected": False, "landmarks": None, "face_confidence": 0.0},
            ),
            gate=gate,
            context_builder=_FixedContextBuilder(),
            vlm_model=vlm,
            visual_observer=observer,
        )

        samples = [item async for item in source.samples()]

        self.assertEqual(samples, [])
        self.assertEqual(gate.evaluate_calls, 0)
        self.assertIsNone(vlm.last_frame)
        self.assertEqual([name for name, _payload in observer.calls], ["observe_frame"])
        observed = observer.calls[0][1]
        self.assertEqual(observed["gate_diagnostics"]["result"]["reason"], "no_face")
        self.assertFalse(observed["gate_diagnostics"]["result"]["should_trigger"])

    async def test_visual_observer_failure_does_not_break_runtime_sample(self):
        gate = _AlwaysTriggerGate()
        observer = _RecordingObserver(fail=True)
        source = VLMGatedCameraEmotionSource(
            frame_source=_OneFrameSource({"frame_id": 1, "timestamp_ms": 123, "payload": None}),
            cv_pipeline=_FixedCvPipeline({
                "frame_id": 1,
                "timestamp_ms": 123,
                "emotion_tag": "tired",
                "fatigue_score": 80.0,
            }),
            gate=gate,
            context_builder=_FixedContextBuilder(),
            vlm_model=_FixedVlm({"expression_label": "tired"}),
            visual_observer=observer,
        )

        samples = [item async for item in source.samples()]

        self.assertEqual(len(samples), 1)
        self.assertTrue(samples[0]["vlm_triggered"])
        self.assertEqual(gate.evaluate_calls, 1)
        self.assertEqual([name for name, _payload in observer.calls], ["observe_frame"])

    async def test_openface_continues_while_single_vlm_request_runs(self):
        gate = _AlwaysTriggerGate()
        observer = _RecordingObserver()
        vlm = _BlockingVlm()
        source = VLMGatedCameraEmotionSource(
            frame_source=_TwoFrameSource(),
            cv_pipeline=_FixedCvPipeline({
                "emotion_tag": "tired",
                "confidence": 0.8,
                "fatigue_score": 80.0,
            }),
            gate=gate,
            context_builder=_FixedContextBuilder(),
            vlm_model=vlm,
            visual_observer=observer,
        )

        collect_task = asyncio.create_task(self._collect_samples(source))
        await asyncio.wait_for(asyncio.to_thread(vlm.started.wait, 1), timeout=1.5)
        for _ in range(20):
            if sum(name == "observe_frame" for name, _ in observer.calls) >= 2:
                break
            await asyncio.sleep(0.01)
        observed_while_running = sum(name == "observe_frame" for name, _ in observer.calls)
        vlm.release.set()
        samples = await asyncio.wait_for(collect_task, timeout=2)

        self.assertEqual(observed_while_running, 2)
        self.assertEqual(gate.evaluate_calls, 2)
        self.assertEqual(vlm.calls, 1)
        self.assertEqual(len(samples), 1)

    @staticmethod
    async def _collect_samples(source):
        return [item async for item in source.samples()]


if __name__ == "__main__":
    unittest.main()
