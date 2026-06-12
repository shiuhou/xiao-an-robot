"""Manually test OpenClaw tool_calls through XiaoAnBrain and ActionExecutor."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


def build_tool_call(tool: str, text: str) -> OpenClawToolCall:
    if tool == "note.add":
        return OpenClawToolCall(
            name="note.add",
            arguments={"content": text, "tags": ["manual-test"]},
        )
    if tool == "work_context.record":
        return OpenClawToolCall(
            name="work_context.record",
            arguments={"content": text, "source": "manual-test"},
        )
    return OpenClawToolCall(
        name="summary.daily",
        arguments={"date": "today"},
    )


def build_event(event_type: str, text: str) -> dict:
    return {
        "type": event_type,
        "payload": {
            "text": text,
            "session_id": "manual-tool-test",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test local OpenClaw tool_calls without a real OpenClaw server.")
    parser.add_argument(
        "--event-type",
        choices=["frontend.message", "asr.transcript"],
        default="frontend.message",
        help="Event type to send to XiaoAnBrain.",
    )
    parser.add_argument("--text", default="帮我记一下明天下午交报告", help="Event text.")
    parser.add_argument(
        "--tool",
        choices=["note.add", "work_context.record", "summary.daily"],
        default="note.add",
        help="Fake OpenClaw tool_call to execute.",
    )
    parser.add_argument("--verbose", action="store_true", help="Accepted for local debugging; output is always JSON.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    fake_robot = FakeRobotMotionSkill()
    action_executor = ActionExecutor(robot_motion_skill=fake_robot)
    fake_adapter = FakeOpenClawAdapter(
        decision=OpenClawDecision(
            handled=True,
            reply_text="我已经帮你处理了。",
            tool_calls=[build_tool_call(args.tool, args.text)],
        ),
    )
    brain = XiaoAnBrain(
        openclaw_adapter=fake_adapter,
        action_executor=action_executor,
    )
    try:
        result = await brain.handle_event(build_event(args.event_type, args.text))
        output = {
            "event_type": args.event_type,
            "tool": args.tool,
            "result": result,
            "fake_robot_calls": fake_robot.calls,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        brain.close()


if __name__ == "__main__":
    asyncio.run(main())
