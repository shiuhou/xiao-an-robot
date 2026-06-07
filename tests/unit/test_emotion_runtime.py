"""Unit tests for emotion_runtime model backend selection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from base_station.monitor.emotion_runtime import (
    BaseStationEmotionRuntime,
    create_emotion_source,
    create_face_emotion_model,
    parse_args,
)
from base_station.perception.openvino_qwen_vl_emotion_model import OpenVINOQwenVLEmotionModel
from base_station.perception.qwen_vl_emotion_model import FakeQwenVLEmotionModel


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


class EmotionRuntimeBackendTest(unittest.IsolatedAsyncioTestCase):
    async def test_openvino_qwen_vl_is_legal_model_backend_arg(self) -> None:
        args = parse_args(["--model-backend", "openvino_qwen_vl"])

        self.assertEqual(args.model_backend, "openvino_qwen_vl")

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


if __name__ == "__main__":
    unittest.main()
