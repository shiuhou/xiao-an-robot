"""Unit tests for the WebSocket video runtime runner."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
