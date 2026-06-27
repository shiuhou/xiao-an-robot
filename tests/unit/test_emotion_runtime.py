"""Unit tests for emotion_runtime model backend selection."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from base_station.monitor.emotion_runtime import (
    BaseStationEmotionRuntime,
    VLMGatedCameraEmotionSource,
    create_emotion_source,
    create_face_emotion_model,
    create_vlm_emotion_model,
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


class EmotionRuntimeBackendTest(unittest.IsolatedAsyncioTestCase):
    async def test_vlm_gate_args_are_available(self) -> None:
        args = parse_args([
            "--enable-vlm-gate",
            "--vlm-backend",
            "openvino_qwen_vl",
            "--vlm-model-path",
            "models/qwen-vl-openvino",
            "--force-vlm",
        ])

        self.assertTrue(args.enable_vlm_gate)
        self.assertEqual(args.vlm_backend, "openvino_qwen_vl")
        self.assertEqual(args.vlm_model_path, "models/qwen-vl-openvino")
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
        )

        self.assertIsInstance(model, OpenVINOQwenVLEmotionModel)
        self.assertEqual(model.runner.model_dir, "models/qwen-vl-openvino")
        self.assertEqual(model.runner.device, "GPU")

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


class _FixedCvPipeline:
    def __init__(self, cv_sample):
        self._cv = cv_sample

    def process_frame(self, frame):
        return dict(self._cv)


class _AlwaysTriggerGate:
    def evaluate(self, cv_sample, force_vlm=False):
        return {"should_trigger": True, "reason": "test"}


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

        # Runtime delivery keeps CV's top-level decision fields and nests VLM.
        self.assertEqual(sample["emotion_tag"], "neutral")
        self.assertTrue(sample["vlm_triggered"])
        self.assertEqual(sample["vlm_trigger_reason"], "test")
        self.assertEqual(sample["vlm"], {
            "executed": True,
            "status": "ok",
            "expression_label": "tired",
            "emotion_tag": "tired",
            "confidence": 0.9,
            "fatigue_score": 0.8,
            "visual_reason": "eyes heavy",
            "vlm_observation": "needs rest",
            "evidence": [],
            "face_observation": "needs rest",
            "message": "",
        })
        # CV fatigue fields are not overwritten by the VLM result.
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
            "confidence": None,
            "fatigue_score": None,
            "visual_reason": "",
            "vlm_observation": "",
            "evidence": [],
            "face_observation": "",
            "message": "",
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


if __name__ == "__main__":
    unittest.main()
