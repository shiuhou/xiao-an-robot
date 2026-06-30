"""Run the reminder scheduler against a XiaoAnMemoryStore database."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.core.memory import XiaoAnMemoryStore
from agent.core.reminder_scheduler import ReminderScheduler


DEFAULT_DB_PATH = PROJECT_ROOT / "agent" / "data" / "manual_tool_test.db"


class DryRunRobot:
    def __init__(self) -> None:
        self.calls = []

    async def say(self, text: str) -> dict:
        self.calls.append(("say", text))
        return {"ok": True, "dry_run": True, "text": text}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Xiao An reminder scheduler.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="XiaoAnMemoryStore database path.")
    parser.add_argument("--poll-interval-sec", type=float, default=1.0, help="Polling interval.")
    parser.add_argument("--once", action="store_true", help="Run one tick and exit.")
    parser.add_argument("--verbose", action="store_true", help="Print JSON tick output.")
    parser.add_argument(
        "--execute-robot",
        action="store_true",
        help="Use RobotMotionSkill instead of dry-run robot.",
    )
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/agent", help="Robot gateway URL.")
    return parser.parse_args(argv)


def build_robot(args: argparse.Namespace):
    if not args.execute_robot:
        return DryRunRobot()

    from agent.core.gateway import RobotGateway
    from agent.skills.robot_motion import RobotMotionSkill

    return RobotMotionSkill(gateway=RobotGateway(url=args.gateway_url))


async def run(args: argparse.Namespace) -> dict | None:
    store = XiaoAnMemoryStore(db_path=args.db_path)
    scheduler = ReminderScheduler(
        memory_store=store,
        robot_motion=build_robot(args),
        poll_interval_sec=args.poll_interval_sec,
    )
    try:
        if args.once:
            result = await scheduler.tick()
            if args.verbose:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return result
        await scheduler.run_forever()
        return None
    finally:
        scheduler.close()
        store.close()


def main(argv: list[str] | None = None) -> None:
    asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    main()
