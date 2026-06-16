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


DEFAULT_MEMORY_DB_PATH = PROJECT_ROOT / "agent" / "data" / "manual_tool_test.db"


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


def build_tool_call(
    tool: str,
    text: str,
    delay_seconds: int | None = None,
    task_id: int | None = None,
) -> OpenClawToolCall:
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
    if tool == "reminder.add":
        return OpenClawToolCall(
            name="reminder.add",
            arguments={
                "message": text,
                "delay_seconds": delay_seconds if delay_seconds is not None else 60,
            },
        )
    if tool == "reminder.query":
        return OpenClawToolCall(
            name="reminder.query",
            arguments={"include_fired": True},
        )
    if tool == "reminder.cancel":
        return OpenClawToolCall(
            name="reminder.cancel",
            arguments={"message_contains": text},
        )
    if tool == "task.add":
        return OpenClawToolCall(
            name="task.add",
            arguments={"title": text},
        )
    if tool == "task.query":
        return OpenClawToolCall(
            name="task.query",
            arguments={"include_done": True},
        )
    if tool == "task.complete":
        arguments = {"title_contains": text}
        if task_id is not None:
            arguments["task_id"] = task_id
        return OpenClawToolCall(
            name="task.complete",
            arguments=arguments,
        )
    if tool == "task.cancel":
        arguments = {"title_contains": text}
        if task_id is not None:
            arguments["task_id"] = task_id
        return OpenClawToolCall(
            name="task.cancel",
            arguments=arguments,
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
        choices=[
            "note.add",
            "work_context.record",
            "summary.daily",
            "reminder.add",
            "reminder.query",
            "reminder.cancel",
            "task.add",
            "task.query",
            "task.complete",
            "task.cancel",
        ],
        default="note.add",
        help="Fake OpenClaw tool_call to execute.",
    )
    parser.add_argument("--delay-seconds", type=int, default=None, help="Delay for reminder.add.")
    parser.add_argument("--task-id", type=int, default=None, help="Task id for task.complete/task.cancel.")
    parser.add_argument("--verbose", action="store_true", help="Accepted for local debugging; output is always JSON.")
    parser.add_argument("--record-memory", action="store_true", help="Record tool calls into a test XiaoAnMemoryStore.")
    parser.add_argument("--db-path", default=None, help="Database path for --record-memory.")
    parser.add_argument(
        "--fresh-db",
        action="store_true",
        help="Delete the selected test database before running when --record-memory is enabled.",
    )
    parser.add_argument("--memory-limit", type=int, default=10, help="Recent memory rows to include in output.")
    return parser.parse_args(argv)


def _resolve_memory_db_path(args: argparse.Namespace) -> Path:
    if args.db_path:
        return Path(args.db_path).expanduser().resolve()
    return DEFAULT_MEMORY_DB_PATH.resolve()


def _prepare_memory_store(args: argparse.Namespace):
    if not args.record_memory:
        return None, None

    from agent.core.memory import XiaoAnMemoryStore

    db_path = _resolve_memory_db_path(args)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh_db and db_path.exists():
        explicit_db_path = args.db_path is not None
        default_test_db = db_path == DEFAULT_MEMORY_DB_PATH.resolve()
        if explicit_db_path or default_test_db:
            db_path.unlink()
    return XiaoAnMemoryStore(db_path=str(db_path)), db_path


def _safe_snapshot_call(memory_store, method_name: str, memory_errors: list[dict], **kwargs):
    method = getattr(memory_store, method_name, None)
    if not callable(method):
        return None
    try:
        return method(**kwargs)
    except Exception as exc:
        memory_errors.append({"scope": method_name, "error": str(exc)})
        return None


def build_memory_snapshot(memory_store, db_path: Path, memory_limit: int) -> dict:
    memory_errors: list[dict] = []
    snapshot = {
        "db_path": str(db_path),
        "recent_events": _safe_snapshot_call(
            memory_store,
            "query_recent_events",
            memory_errors,
            limit=memory_limit,
        ),
        "recent_tool_runs": _safe_snapshot_call(
            memory_store,
            "query_recent_tool_runs",
            memory_errors,
            limit=memory_limit,
        ),
        "recent_notes": _safe_snapshot_call(
            memory_store,
            "query_recent_notes",
            memory_errors,
            limit=memory_limit,
        ),
        "recent_summaries": _safe_snapshot_call(
            memory_store,
            "query_recent_summaries",
            memory_errors,
            limit=memory_limit,
        ),
        "recent_work_activities": _safe_snapshot_call(
            memory_store,
            "query_recent_work_activities",
            memory_errors,
            limit=memory_limit,
        ),
        "recent_reminders": _safe_snapshot_call(
            memory_store,
            "query_reminders",
            memory_errors,
            limit=memory_limit,
            include_fired=True,
        ),
        "recent_tasks": _safe_snapshot_call(
            memory_store,
            "query_tasks",
            memory_errors,
            limit=memory_limit,
            include_done=True,
        ),
        "tool_run_summary": _safe_snapshot_call(
            memory_store,
            "get_tool_run_summary",
            memory_errors,
        ),
        "notes_summary": _safe_snapshot_call(
            memory_store,
            "get_notes_summary",
            memory_errors,
        ),
        "summary_overview": _safe_snapshot_call(
            memory_store,
            "get_summary_overview",
            memory_errors,
        ),
        "reminders_summary": _safe_snapshot_call(
            memory_store,
            "get_reminders_summary",
            memory_errors,
        ),
        "tasks_summary": _safe_snapshot_call(
            memory_store,
            "get_tasks_summary",
            memory_errors,
        ),
    }
    if memory_errors:
        snapshot["memory_errors"] = memory_errors
    return snapshot


async def run(args: argparse.Namespace) -> dict:
    memory_store, memory_db_path = _prepare_memory_store(args)
    fake_robot = FakeRobotMotionSkill()
    if memory_store is None:
        action_executor = ActionExecutor(robot_motion_skill=fake_robot)
    else:
        action_executor = ActionExecutor(robot_motion_skill=fake_robot, memory_store=memory_store)
    fake_adapter = FakeOpenClawAdapter(
        decision=OpenClawDecision(
            handled=True,
            reply_text="我已经帮你处理了。",
            tool_calls=[build_tool_call(args.tool, args.text, args.delay_seconds, args.task_id)],
        ),
    )
    brain_kwargs = {
        "openclaw_adapter": fake_adapter,
        "action_executor": action_executor,
    }
    if memory_store is not None:
        brain_kwargs["db_path"] = str(memory_db_path)
        brain_kwargs["context_memory"] = memory_store
    brain = XiaoAnBrain(**brain_kwargs)
    try:
        result = await brain.handle_event(build_event(args.event_type, args.text))
        output = {
            "event_type": args.event_type,
            "tool": args.tool,
            "result": result,
            "fake_robot_calls": fake_robot.calls,
        }
        if memory_store is not None:
            output["memory_snapshot"] = build_memory_snapshot(
                memory_store,
                memory_db_path,
                args.memory_limit,
            )
        return output
    finally:
        brain.close()
        if memory_store is not None:
            memory_store.close()


async def main(argv: list[str] | None = None) -> None:
    output = await run(parse_args(argv))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
