"""Unit tests for fake OpenClaw tool_call runtime flow."""

from __future__ import annotations

import unittest

from agent.core.action_executor import ActionExecutor
from agent.core.brain import XiaoAnBrain
from agent.core.openclaw_adapter import FakeOpenClawAdapter, OpenClawDecision, OpenClawToolCall


class FakeRobotMotionSkill:
    def __init__(self) -> None:
        self.calls = []

    async def say(self, text: str) -> dict:
        self.calls.append(("say", text))
        return {"ok": True, "text": text}

    async def show_expression(self, expression: str) -> dict:
        self.calls.append(("expression", expression))
        return {"ok": True, "expression": expression}

    async def move_out_of_dock(self) -> dict:
        self.calls.append(("move_out_of_dock", None))
        return {"ok": True}

    async def return_to_dock(self) -> dict:
        self.calls.append(("return_to_dock", None))
        return {"ok": True}


class FakeMemory:
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

    def close(self) -> None:
        pass


class OpenClawToolCallRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def build_brain(self, decision: OpenClawDecision, fake_robot: FakeRobotMotionSkill) -> XiaoAnBrain:
        return XiaoAnBrain(
            gateway=None,
            memory=FakeMemory(),
            openclaw_adapter=FakeOpenClawAdapter(decision=decision),
            action_executor=ActionExecutor(robot_motion_skill=fake_robot),
        )

    async def test_frontend_message_executes_note_add_tool_call(self) -> None:
        fake_robot = FakeRobotMotionSkill()
        brain = self.build_brain(
            OpenClawDecision(
                handled=True,
                reply_text="我已经帮你处理了。",
                tool_calls=[
                    OpenClawToolCall(
                        name="note.add",
                        arguments={"content": "帮我记一下明天下午交报告", "tags": ["manual-test"]},
                    ),
                ],
            ),
            fake_robot,
        )

        result = await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "帮我记一下明天下午交报告", "session_id": "test-session"},
        })

        self.assertTrue(result["handled"])
        self.assertEqual(result["route"], "frontend_openclaw")
        self.assertEqual(fake_robot.calls, [("say", "我已经帮你处理了。")])
        note_action = next(action for action in result["executed_actions"] if action["name"] == "note.add")
        self.assertTrue(note_action["result"]["ok"])
        self.assertEqual(note_action["result"]["result"]["content"], "帮我记一下明天下午交报告")

    async def test_asr_transcript_executes_work_context_record_tool_call(self) -> None:
        fake_robot = FakeRobotMotionSkill()
        brain = self.build_brain(
            OpenClawDecision(
                handled=True,
                reply_text="我已经帮你处理了。",
                tool_calls=[
                    OpenClawToolCall(
                        name="work_context.record",
                        arguments={"content": "帮我记录当前工作", "source": "manual-test"},
                    ),
                ],
            ),
            fake_robot,
        )

        result = await brain.handle_event({
            "type": "asr.transcript",
            "payload": {"text": "帮我记录当前工作", "session_id": "test-session"},
        })

        self.assertEqual(result["route"], "link_1_openclaw")
        self.assertEqual(fake_robot.calls, [("say", "我已经帮你处理了。")])
        work_action = next(action for action in result["executed_actions"] if action["name"] == "work_context.record")
        self.assertTrue(work_action["result"]["ok"])
        self.assertEqual(work_action["result"]["result"]["source"], "manual-test")

    async def test_summary_daily_tool_call_executes_placeholder(self) -> None:
        fake_robot = FakeRobotMotionSkill()
        brain = self.build_brain(
            OpenClawDecision(
                handled=True,
                reply_text="我已经帮你处理了。",
                tool_calls=[
                    OpenClawToolCall(
                        name="summary.daily",
                        arguments={"date": "today"},
                    ),
                ],
            ),
            fake_robot,
        )

        result = await brain.handle_event({
            "type": "frontend.message",
            "payload": {"text": "生成今天总结", "session_id": "test-session"},
        })

        summary_action = next(action for action in result["executed_actions"] if action["name"] == "summary.daily")
        self.assertEqual(summary_action["result"]["result"]["status"], "placeholder")
        self.assertEqual(fake_robot.calls, [("say", "我已经帮你处理了。")])


if __name__ == "__main__":
    unittest.main()
