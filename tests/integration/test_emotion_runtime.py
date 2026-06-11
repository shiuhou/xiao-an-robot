"""Integration-style tests for base_station.monitor.emotion_runtime."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from base_station.monitor.emotion_event_loop import EmotionEventLoop
from base_station.monitor.emotion_runtime import (
    BaseStationEmotionRuntime,
    IntervalEmotionSource,
    LimitedEmotionSource,
    create_face_emotion_model,
    create_emotion_source,
    create_fake_face_runtime,
    create_runtime,
    runtime_db_path,
    run_cli,
)
from base_station.perception.face_emotion_model import MockFaceEmotionModel
from base_station.perception.face_emotion_pipeline import CameraEmotionSource
from base_station.perception.fake_face_emotion import FakeFaceEmotionSource
from unittest.mock import patch


class FakeBrain:
    def __init__(self) -> None:
        self.events = []
        self.closed = False

    async def handle_event(self, event: dict) -> dict:
        self.events.append(event)
        return {
            "handled": False,
            "reason": "fake",
            "message": "fake brain handled event",
        }

    def close(self) -> None:
        self.closed = True


class FakeOpenCVCameraFrameSource:
    instances: list["FakeOpenCVCameraFrameSource"] = []

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
        FakeOpenCVCameraFrameSource.instances.append(self)

    async def frames(self):
        frame_id = 1
        try:
            while True:
                yield {
                    "source": "opencv_camera",
                    "frame_id": frame_id,
                    "timestamp_ms": 1000 + frame_id,
                    "width": self.width or 640,
                    "height": self.height or 480,
                    "payload": f"frame-{frame_id}",
                }
                frame_id += 1
        finally:
            self.closed = True

    def close(self) -> None:
        self.closed = True


class FakeRuntime:
    instances: list["FakeRuntime"] = []

    def __init__(self) -> None:
        self.event_loop = type("FakeEventLoop", (), {"brain": FakeBrain()})()
        self.ran = False
        FakeRuntime.instances.append(self)

    async def run(self) -> list[dict]:
        self.ran = True
        return []


class FakeOpenVINOFaceEmotionModel:
    instances: list["FakeOpenVINOFaceEmotionModel"] = []

    def __init__(self, model_path: str, device: str = "CPU") -> None:
        self.model_path = model_path
        self.device = device
        FakeOpenVINOFaceEmotionModel.instances.append(self)

    def predict(self, frame: dict) -> dict:
        return {
            "emotion_tag": "anxious",
            "confidence": 0.88,
            "fatigue_score": 0.4,
        }


class EmotionRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_can_create_fake_face_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = create_fake_face_runtime(
                pattern="neutral",
                count=1,
                interval_seconds=0,
                db_path=str(Path(temp_dir) / "runtime.db"),
                verbose=False,
            )
            try:
                self.assertIsInstance(runtime, BaseStationEmotionRuntime)
                self.assertIsInstance(runtime.source, FakeFaceEmotionSource)
                self.assertIsInstance(runtime.event_loop, EmotionEventLoop)
            finally:
                runtime.event_loop.brain.close()

    async def test_can_create_fake_camera_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = create_runtime(
                source_name="fake_camera",
                pattern="neutral",
                count=1,
                interval_seconds=0,
                db_path=str(Path(temp_dir) / "runtime.db"),
                verbose=False,
            )
            try:
                self.assertIsInstance(runtime, BaseStationEmotionRuntime)
                self.assertIsInstance(runtime.source, CameraEmotionSource)
                self.assertIsInstance(runtime.event_loop, EmotionEventLoop)
            finally:
                runtime.event_loop.brain.close()

    async def test_can_create_opencv_camera_runtime(self) -> None:
        FakeOpenCVCameraFrameSource.instances = []
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "base_station.monitor.emotion_runtime.OpenCVCameraFrameSource",
                FakeOpenCVCameraFrameSource,
            ):
                runtime = create_runtime(
                    source_name="opencv_camera",
                    pattern="neutral",
                    count=1,
                    interval_seconds=0,
                    db_path=str(Path(temp_dir) / "runtime.db"),
                    verbose=False,
                    camera_index=2,
                    camera_width=800,
                    camera_height=600,
                )
            try:
                self.assertIsInstance(runtime, BaseStationEmotionRuntime)
                self.assertIsInstance(runtime.source, LimitedEmotionSource)
                self.assertIsInstance(runtime.event_loop, EmotionEventLoop)
                camera = FakeOpenCVCameraFrameSource.instances[0]
                self.assertEqual(camera.camera_index, 2)
                self.assertEqual(camera.width, 800)
                self.assertEqual(camera.height, 600)
            finally:
                runtime.event_loop.brain.close()

    async def test_unsupported_source_reports_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported emotion source"):
            create_emotion_source(
                source="camera",
                pattern="tired",
                count=1,
                interval_seconds=0,
            )

    async def test_default_model_backend_for_camera_sources_is_mock(self) -> None:
        source = create_emotion_source(
            source="fake_camera",
            pattern="tired",
            count=1,
            interval_seconds=0,
        )

        self.assertIsInstance(source.pipeline.model, MockFaceEmotionModel)

    async def test_openvino_backend_reports_missing_default_models(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "OpenVINO CV model"):
            create_face_emotion_model(
                model_backend="openvino",
                pattern="neutral",
                model_path=None,
                device="CPU",
            )

    async def test_openvino_backend_creates_model_with_path_and_device(self) -> None:
        FakeOpenVINOFaceEmotionModel.instances = []
        with patch(
            "base_station.monitor.emotion_runtime.OpenVINOFaceEmotionModel",
            FakeOpenVINOFaceEmotionModel,
        ):
            source = create_emotion_source(
                source="fake_camera",
                pattern="neutral",
                count=1,
                interval_seconds=0,
                model_backend="openvino",
                model_path="emotion.xml",
                device="GPU",
            )

        self.assertIsInstance(source.pipeline.model, FakeOpenVINOFaceEmotionModel)
        self.assertEqual(FakeOpenVINOFaceEmotionModel.instances[0].model_path, "emotion.xml")
        self.assertEqual(FakeOpenVINOFaceEmotionModel.instances[0].device, "GPU")

    async def test_unsupported_model_backend_reports_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported model backend"):
            create_face_emotion_model(
                model_backend="camera",
                pattern="neutral",
            )

    def test_cli_reports_missing_openvino_models_without_traceback(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            exit_code = run_cli([
                "--source",
                "fake_camera",
                "--model-backend",
                "openvino",
                "--count",
                "1",
                "--interval",
                "0",
            ])

        self.assertEqual(exit_code, 1)
        self.assertIn("Error: OpenVINO CV model", stderr.getvalue())
        self.assertNotIn("No module named 'openvino'", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_reports_missing_model_file_without_traceback(self) -> None:
        stderr = io.StringIO()

        with patch(
            "base_station.monitor.emotion_runtime.OpenVINOFaceEmotionModel",
            side_effect=FileNotFoundError("OpenVINO model path does not exist: missing-model.xml"),
        ):
            with redirect_stderr(stderr):
                exit_code = run_cli([
                    "--source",
                    "fake_camera",
                    "--model-backend",
                    "openvino",
                    "--model-path",
                    "missing-model.xml",
                    "--count",
                    "1",
                    "--interval",
                    "0",
                ])

        self.assertEqual(exit_code, 1)
        self.assertIn("Error:", stderr.getvalue())
        self.assertIn("missing-model.xml", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_normal_mock_backend_path_returns_zero(self) -> None:
        FakeRuntime.instances = []

        with patch("base_station.monitor.emotion_runtime.create_runtime", return_value=FakeRuntime()):
            exit_code = run_cli([
                "--source",
                "opencv_camera",
                "--model-backend",
                "mock",
                "--pattern",
                "neutral",
                "--count",
                "1",
                "--interval",
                "0",
                "--fresh-db",
            ])

        self.assertEqual(exit_code, 0)
        self.assertTrue(FakeRuntime.instances[0].ran)
        self.assertTrue(FakeRuntime.instances[0].event_loop.brain.closed)

    async def test_fresh_db_does_not_use_default_db_path(self) -> None:
        default_path = "agent/data/xiao_an.db"
        with runtime_db_path(default_path, fresh_db=True) as active_db_path:
            self.assertNotEqual(active_db_path, default_path)
            self.assertIn("xiao_an_runtime.db", active_db_path)

        self.assertFalse(Path(active_db_path).exists())

    async def test_runtime_processes_finite_fake_source(self) -> None:
        brain = FakeBrain()
        event_loop = EmotionEventLoop(brain=brain)
        source = FakeFaceEmotionSource(pattern="mixed", count=3, interval_seconds=0)
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        results = await runtime.run()

        self.assertEqual(len(results), 3)
        self.assertEqual(len(brain.events), 3)
        self.assertEqual(
            [event["payload"]["emotion_tag"] for event in brain.events],
            ["neutral", "tired", "tired"],
        )

    async def test_fake_camera_runtime_processes_finite_source(self) -> None:
        brain = FakeBrain()
        event_loop = EmotionEventLoop(brain=brain)
        source = create_emotion_source(
            source="fake_camera",
            pattern="mixed",
            count=3,
            interval_seconds=0,
        )
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        results = await runtime.run()

        self.assertEqual(len(results), 3)
        self.assertEqual(len(brain.events), 3)
        self.assertEqual(
            [event["payload"]["emotion_tag"] for event in brain.events],
            ["neutral", "tired", "tired"],
        )
        self.assertEqual([event["payload"]["source"] for event in brain.events], ["fake_face"] * 3)
        self.assertEqual([event["payload"]["frame_source"] for event in brain.events], ["fake_camera"] * 3)

    async def test_fake_camera_tired_pattern_still_outputs_tired(self) -> None:
        brain = FakeBrain()
        event_loop = EmotionEventLoop(brain=brain)
        source = create_emotion_source(
            source="fake_camera",
            pattern="tired",
            count=2,
            interval_seconds=0,
        )
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        await runtime.run()

        self.assertEqual([event["payload"]["emotion_tag"] for event in brain.events], ["tired", "tired"])
        self.assertEqual([event["payload"]["frame_source"] for event in brain.events], ["fake_camera"] * 2)

    async def test_opencv_camera_neutral_pattern_outputs_neutral(self) -> None:
        FakeOpenCVCameraFrameSource.instances = []
        brain = FakeBrain()
        event_loop = EmotionEventLoop(brain=brain)
        with patch(
            "base_station.monitor.emotion_runtime.OpenCVCameraFrameSource",
            FakeOpenCVCameraFrameSource,
        ):
            source = create_emotion_source(
                source="opencv_camera",
                pattern="neutral",
                count=2,
                interval_seconds=0,
            )
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        results = await runtime.run()

        self.assertEqual([event["payload"]["emotion_tag"] for event in brain.events], ["neutral", "neutral"])
        self.assertEqual([event["payload"]["frame_source"] for event in brain.events], ["opencv_camera"] * 2)
        self.assertEqual([result["handled"] for result in results], [False, False])

    async def test_opencv_camera_tired_pattern_outputs_tired(self) -> None:
        FakeOpenCVCameraFrameSource.instances = []
        brain = FakeBrain()
        event_loop = EmotionEventLoop(brain=brain)
        with patch(
            "base_station.monitor.emotion_runtime.OpenCVCameraFrameSource",
            FakeOpenCVCameraFrameSource,
        ):
            source = create_emotion_source(
                source="opencv_camera",
                pattern="tired",
                count=2,
                interval_seconds=0,
            )
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        await runtime.run()

        self.assertEqual([event["payload"]["emotion_tag"] for event in brain.events], ["tired", "tired"])
        self.assertEqual([event["payload"]["frame_source"] for event in brain.events], ["opencv_camera"] * 2)

    async def test_opencv_camera_runtime_processes_finite_source(self) -> None:
        FakeOpenCVCameraFrameSource.instances = []
        brain = FakeBrain()
        event_loop = EmotionEventLoop(brain=brain)
        with patch(
            "base_station.monitor.emotion_runtime.OpenCVCameraFrameSource",
            FakeOpenCVCameraFrameSource,
        ):
            source = create_emotion_source(
                source="opencv_camera",
                pattern="mixed",
                count=3,
                interval_seconds=0,
                camera_index=1,
                camera_width=320,
                camera_height=240,
            )
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        results = await runtime.run()

        self.assertEqual(len(results), 3)
        self.assertEqual(len(brain.events), 3)
        self.assertEqual(
            [event["payload"]["emotion_tag"] for event in brain.events],
            ["neutral", "tired", "tired"],
        )
        self.assertEqual([event["payload"]["source"] for event in brain.events], ["fake_face"] * 3)
        self.assertEqual([event["payload"]["frame_source"] for event in brain.events], ["opencv_camera"] * 3)
        self.assertTrue(FakeOpenCVCameraFrameSource.instances[0].closed)

    async def test_opencv_camera_runtime_obeys_interval(self) -> None:
        FakeOpenCVCameraFrameSource.instances = []
        brain = FakeBrain()
        event_loop = EmotionEventLoop(brain=brain)
        with patch(
            "base_station.monitor.emotion_runtime.OpenCVCameraFrameSource",
            FakeOpenCVCameraFrameSource,
        ):
            source = create_emotion_source(
                source="opencv_camera",
                pattern="neutral",
                count=3,
                interval_seconds=1.5,
            )
        runtime = BaseStationEmotionRuntime(source=source, event_loop=event_loop, verbose=False)

        with patch("base_station.monitor.emotion_runtime.asyncio.sleep") as sleep:
            results = await runtime.run()

        self.assertIsInstance(source, LimitedEmotionSource)
        self.assertIsInstance(source.source, IntervalEmotionSource)
        self.assertEqual(len(results), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.5, 1.5])


if __name__ == "__main__":
    unittest.main()
