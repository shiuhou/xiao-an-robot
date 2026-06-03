"""Integration-style tests for base_station.monitor.emotion_runtime."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from base_station.monitor.emotion_event_loop import EmotionEventLoop
from base_station.monitor.emotion_runtime import (
    BaseStationEmotionRuntime,
    create_emotion_source,
    create_fake_face_runtime,
    create_runtime,
    runtime_db_path,
)
from base_station.perception.face_emotion_pipeline import CameraEmotionSource
from base_station.perception.fake_face_emotion import FakeFaceEmotionSource


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

    async def test_unsupported_source_reports_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported emotion source"):
            create_emotion_source(
                source="camera",
                pattern="tired",
                count=1,
                interval_seconds=0,
            )

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


if __name__ == "__main__":
    unittest.main()
