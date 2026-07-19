"""Unit tests for the ASR "汇总屏幕使用" -> screen report push route."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from agent.core.memory import XiaoAnMemoryStore
from agent.core.openclaw_adapter import FakeOpenClawAdapter
from agent.core.work_mode import WorkModeStore


class FakeGateway:
    async def send_expression(self, expression: str, duration_ms: int = 3000, loop: bool = False) -> dict:
        return {"type": "agent.ack", "payload": {"ok": True}}

    async def send_motion(self, action: str, params: dict | None = None, timeout_ms: int = 5000) -> dict:
        return {"type": "agent.ack", "payload": {"ok": True}}

    async def send_tts(self, text: str) -> dict:
        return {"type": "agent.ack", "payload": {"ok": True}}


class FakeMemory:
    def insert_emotion(self, *args, **kwargs) -> int:
        return 1

    def get_recent_summary(self, seconds: int = 300, now_ms: int | None = None) -> dict:
        return {"count": 0, "avg_fatigue_score": 0.0, "max_confidence": 0.0,
                "top_emotion": None, "emotions_count": {}}

    def close(self) -> None:
        pass


class XiaoAnBrainScreenReportTest(unittest.IsolatedAsyncioTestCase):
    async def test_asr_screen_report_pushes_prepared_markdown_to_openclaw(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = XiaoAnMemoryStore(db_path=str(root / "xiao_an.db"))
            store.insert_event(
                event_type="screen.usage_summary",
                source="screen",
                payload={
                    "generated_at_ms": int(time.time() * 1000),
                    "active_seconds": 3600,
                    "away_seconds": 300,
                    "session_count": 5,
                    "longest_session_seconds": 1200,
                    "total_keys": 100,
                    "by_app": [{"app": "Code.exe", "seconds": 3600}],
                },
            )
            openclaw_adapter = FakeOpenClawAdapter()
            brain = XiaoAnBrain(
                gateway=FakeGateway(),
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                context_memory=store,
                work_mode_store=WorkModeStore(root / "work_mode.json", cooldown_seconds=0),
            )
            try:
                result = await brain.handle_event({
                    "type": "asr.transcript",
                    "payload": {"text": "小安，汇总屏幕使用时间"},
                })
            finally:
                store.close()

        self.assertEqual(result["route"], "link_1_screen_report")
        self.assertEqual(result["reason"], "screen_report_push")
        self.assertTrue(result["screen_report"]["has_usage"])
        self.assertIn("屏幕使用报告", result["screen_report"]["title"])

        self.assertEqual(len(openclaw_adapter.events), 1)
        event = openclaw_adapter.events[0]
        self.assertEqual(event.type, "screen.report")
        self.assertIn("飞书新建", event.text)
        pushed = event.context["screen_report"]
        self.assertIn("## 总览", pushed["markdown"])
        self.assertIn("Code.exe", pushed["markdown"])

    async def test_unrelated_asr_text_does_not_take_screen_report_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = XiaoAnMemoryStore(db_path=str(root / "xiao_an.db"))
            openclaw_adapter = FakeOpenClawAdapter()
            brain = XiaoAnBrain(
                gateway=FakeGateway(),
                memory=FakeMemory(),
                openclaw_adapter=openclaw_adapter,
                context_memory=store,
                work_mode_store=WorkModeStore(root / "work_mode.json", cooldown_seconds=0),
            )
            try:
                result = await brain.handle_event({
                    "type": "asr.transcript",
                    "payload": {"text": "今天天气怎么样"},
                })
            finally:
                store.close()

        self.assertNotEqual(result.get("route"), "link_1_screen_report")


if __name__ == "__main__":
    unittest.main()
