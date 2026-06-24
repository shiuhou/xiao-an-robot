"""Standalone fake work activity runtime for unified memory testing."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

from agent.core.memory import XiaoAnMemoryStore
from base_station.perception.work_activity import FakeWorkActivitySource, PATTERN_SAMPLES


@contextmanager
def runtime_db_path(db_path: str, fresh_db: bool):
    if fresh_db:
        with tempfile.TemporaryDirectory(prefix="xiao_an_work_activity_") as temp_dir:
            yield str(Path(temp_dir) / "xiao_an_work_activity.db")
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    yield db_path


def insert_sample(memory_store: XiaoAnMemoryStore, sample: dict[str, Any]) -> dict[str, int]:
    return memory_store.insert_work_activity(
        source=str(sample.get("source") or "unknown"),
        app_name=str(sample.get("app_name") or ""),
        window_title=str(sample.get("window_title") or ""),
        activity_type=str(sample.get("activity_type") or "unknown"),
        project_hint=sample.get("project_hint"),
        confidence=float(sample.get("confidence") or 0.0),
        duration_seconds=sample.get("duration_seconds"),
        timestamp_ms=sample.get("timestamp_ms"),
    )


def run_samples(
    pattern: str = "coding",
    count: int = 1,
    interval: float = 0.0,
    db_path: str = "agent/data/xiao_an.db",
    fresh_db: bool = False,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    source = FakeWorkActivitySource(pattern=pattern, duration_seconds=interval if interval > 0 else None)
    with runtime_db_path(db_path, fresh_db) as active_db_path:
        with XiaoAnMemoryStore(active_db_path) as memory_store:
            for index in range(count):
                sample = source.next_sample().to_dict()
                insert_result = insert_sample(memory_store, sample)
                summary = memory_store.get_recent_work_summary()
                output = {
                    "sample": sample,
                    "insert_result": insert_result,
                    "summary": summary,
                }
                outputs.append(output)
                if verbose:
                    print(json.dumps(output, ensure_ascii=False, indent=2))
                if interval > 0 and index < count - 1:
                    time.sleep(interval)
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fake work activity samples into Xiao An memory.")
    parser.add_argument("--pattern", choices=sorted(PATTERN_SAMPLES), default="coding")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.0)
    parser.add_argument("--db-path", default="agent/data/xiao_an.db")
    parser.add_argument("--fresh-db", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(args: argparse.Namespace | None = None) -> list[dict[str, Any]]:
    if args is None:
        args = parse_args()
    return run_samples(
        pattern=args.pattern,
        count=args.count,
        interval=args.interval,
        db_path=args.db_path,
        fresh_db=args.fresh_db,
        verbose=args.verbose,
    )


def run_cli(argv: list[str] | None = None) -> int:
    try:
        main(parse_args(argv))
    except KeyboardInterrupt:
        raise
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
