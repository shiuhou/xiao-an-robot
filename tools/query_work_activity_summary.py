"""Query recent work activities and summary from Xiao An memory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.core.memory import XiaoAnMemoryStore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Xiao An recent work activity summary.")
    parser.add_argument("--db-path", default="agent/data/xiao_an.db", help="SQLite database path.")
    parser.add_argument("--limit", type=int, default=20, help="Number of recent activities to include.")
    return parser.parse_args(argv)


def main(args: argparse.Namespace | None = None) -> dict:
    if args is None:
        args = parse_args()

    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with XiaoAnMemoryStore(str(db_path)) as memory_store:
        output = {
            "recent_work_activities": memory_store.query_recent_work_activities(limit=args.limit),
            "summary": memory_store.get_recent_work_summary(limit=args.limit),
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


if __name__ == "__main__":
    main()
