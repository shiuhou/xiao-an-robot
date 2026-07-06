"""Unit tests for the WebSocket video runtime runner."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tools import run_ws_video_runtime


class RunWsVideoRuntimeTest(unittest.TestCase):
    def test_parse_args_accepts_mock_smoke_options(self) -> None:
        args = run_ws_video_runtime.parse_args([
            "--no-agent",
            "--model-backend",
            "mock",
            "--vlm-backend",
            "fake",
            "--force-vlm",
            "--verbose",
        ])

        self.assertTrue(args.no_agent)
        self.assertEqual(args.model_backend, "mock")
        self.assertEqual(args.vlm_backend, "fake")
        self.assertTrue(args.force_vlm)
        self.assertTrue(args.verbose)
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 8765)
        self.assertEqual(args.queue_size, 2)
        self.assertEqual(args.visual_trace_dir, "runtime/integration_console/visual")
        self.assertEqual(args.visual_trace_fps, 2.0)
        self.assertFalse(args.no_visual_trace)

    def test_parse_args_rejects_visual_trace_fps_above_cap(self) -> None:
        with self.assertRaises(SystemExit):
            run_ws_video_runtime.parse_args(["--visual-trace-fps", "2.1"])

    def test_runtime_passes_visual_publisher_to_gated_source(self) -> None:
        args = run_ws_video_runtime.parse_args([
            "--no-agent",
            "--model-backend", "mock",
            "--vlm-backend", "fake",
            "--visual-trace-dir", "runtime/test-visual",
            "--visual-trace-fps", "1.0",
        ])
        frame_source = object()

        with (
            patch.object(run_ws_video_runtime, "build_cv_pipeline", return_value=object()),
            patch.object(run_ws_video_runtime, "create_vlm_emotion_model", return_value=object()),
            patch.object(run_ws_video_runtime, "VisualTracePublisher") as publisher_class,
            patch.object(run_ws_video_runtime, "VLMGatedCameraEmotionSource") as source_class,
            patch.object(run_ws_video_runtime, "EmotionEventLoop"),
            patch.object(run_ws_video_runtime, "BaseStationEmotionRuntime"),
        ):
            run_ws_video_runtime.create_ws_video_runtime(args, frame_source, "runtime/test.db")

        publisher_class.assert_called_once_with(
            "runtime/test-visual",
            max_fps=1.0,
        )
        self.assertIs(
            source_class.call_args.kwargs["visual_observer"],
            publisher_class.return_value,
        )


if __name__ == "__main__":
    unittest.main()
