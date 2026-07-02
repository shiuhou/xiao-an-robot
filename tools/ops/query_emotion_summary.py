"""Query recent emotion summary from the local SQLite database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from base_station.monitor.emotion_db import EmotionDB


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Xiao An recent emotion summary.")
    parser.add_argument("--db", default="agent/data/xiao_an.db", help="SQLite database path.")
    parser.add_argument("--seconds", type=int, default=300, help="Recent time window in seconds.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with EmotionDB(str(db_path)) as db:
        summary = db.get_recent_summary(seconds=args.seconds)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
