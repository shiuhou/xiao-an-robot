"""Regression checks for the work-mode desktop assistant acceptance matrix."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.core.brain import XiaoAnBrain
from agent.core.local_fast_path import LocalFastPathRouter
from agent.core.memory import XiaoAnMemoryStore
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision
from agent.core.runtime_workspace_docs import RuntimeWorkspaceDocs
from agent.core.work_mode import WorkModeStore


CASES_PATH = Path("tests/fixtures/work_mode_desktop_acceptance_cases.json")


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def send_expression(self, expression: str, duration_ms: int = 3000, loop: bool = False) -> dict:
        self.calls.append(("expression", expression, duration_ms, loop))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "display.expression"}}

    async def send_motion(self, action: str, params: dict | None = None, timeout_ms: int = 5000) -> dict:
        self.calls.append(("motion", action, params or {}, timeout_ms))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "motion.execute"}}

    async def send_tts(self, text: str) -> dict:
        self.calls.append(("tts", text))
        return {"type": "agent.ack", "payload": {"ok": True, "forwarded_type": "audio.play_tts"}}


class FakeEmotionMemory:
    def insert_emotion(
        self,
        source: str,
        emotion_tag: str,
        confidence: float,
        fatigue_score: float = 0.0,
        timestamp: int | None = None,
    ) -> int:
        return 1

    def get_recent_summary(self, seconds: int = 300, now_ms: int | None = None) -> dict:
        return {
            "count": 0,
            "avg_fatigue_score": 0.0,
            "max_confidence": 0.0,
            "top_emotion": None,
            "emotions_count": {},
        }


def load_cases() -> list[dict]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return [case for case in payload["cases"] if not case.get("manual_only")]


class WorkModeDesktopAcceptanceCasesTest(unittest.IsolatedAsyncioTestCase):
    async def test_acceptance_matrix_routes_match_brain_behavior(self) -> None:
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 15)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace-xiaoan-runtime"
            gateway = FakeGateway()
            openclaw_adapter = FakeOpenClawAdapter(
                decision=OpenClawDecision(
                    handled=True,
                    display_text="验收回复",
                    spoken_text="验收回复",
                    reply_text="验收回复",
                )
            )
            context_memory = XiaoAnMemoryStore(db_path=str(root / "xiaoan.db"))
            brain = XiaoAnBrain(
                gateway=gateway,
                memory=FakeEmotionMemory(),
                openclaw_adapter=openclaw_adapter,
                context_memory=context_memory,
                local_fast_path=LocalFastPathRouter(RuntimeWorkspaceDocs(workspace)),
                work_mode_store=WorkModeStore(root / "work_mode.json", cooldown_seconds=0),
            )

            try:
                for case in cases:
                    with self.subTest(case=case["id"], phrase=case["phrase"]):
                        events_before = len(openclaw_adapter.events)
                        tts_before = sum(1 for call in gateway.calls if call[0] == "tts")

                        result = await brain.handle_event({
                            "type": "asr.transcript",
                            "payload": {
                                "text": case["phrase"],
                                "source": "acceptance_matrix",
                                "session_id": case["id"],
                                "completed_mic_segment": True,
                            },
                        })

                        self.assertEqual(result["route"], case["expected_route"])
                        if case["expected_owner"] == "local":
                            self.assertEqual(len(openclaw_adapter.events), events_before)
                        elif case["expected_owner"] == "openclaw":
                            self.assertGreater(len(openclaw_adapter.events), events_before)
                        else:
                            self.fail(f"unexpected expected_owner: {case['expected_owner']}")

                        if case.get("expect_tts"):
                            self.assertTrue(result.get("tts_text"))
                            self.assertGreater(
                                sum(1 for call in gateway.calls if call[0] == "tts"),
                                tts_before,
                            )
            finally:
                context_memory.close()

            tasks = (workspace / "TASKS.md").read_text(encoding="utf-8")
            schedule = (workspace / "SCHEDULE.md").read_text(encoding="utf-8")
            reminders = json.loads((workspace / "state" / "local_reminders.json").read_text(encoding="utf-8"))

        self.assertIn("- [x] 测试桌面助手验收", tasks)
        self.assertIn("检查桌面助手验收", schedule)
        self.assertIn("喝水", schedule)
        self.assertTrue(any(item["title"] == "喝水" and item["status"] == "cancelled" for item in reminders["items"]))


if __name__ == "__main__":
    unittest.main()
