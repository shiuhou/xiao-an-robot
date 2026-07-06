#!/usr/bin/env python3
"""Forward completed OpenClaw cron reminder runs to XiaoAn's notify API."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_SQLITE_PATH = Path.home() / ".openclaw" / "state" / "openclaw.sqlite"
DEFAULT_NOTIFY_URL = "http://127.0.0.1:8787/api/openclaw/notify"
DEFAULT_STATE_FILE = (
    Path.home()
    / ".openclaw"
    / "workspace-xiaoan-runtime"
    / "state"
    / "cron_delivery_bridge.json"
)
DEFAULT_AGENT_ID = "xiaoan-runtime"
DEFAULT_LOOKBACK_SECONDS = 15 * 60
BRIDGE_SOURCE = "openclaw-cron-bridge"


@dataclass(frozen=True)
class CronRun:
    job_id: str
    seq: int | None
    ts: int | None
    status: str
    summary: str
    run_id: str | None = None
    run_at_ms: int | None = None
    session_key: str | None = None
    entry_json: str | None = None

    @property
    def delivery_key(self) -> str:
        if self.run_id:
            return self.run_id
        if self.run_at_ms is not None:
            return f"{self.job_id}:{self.run_at_ms}"
        if self.seq is not None:
            return f"{self.job_id}:seq:{self.seq}"
        return self.job_id


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def load_delivery_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"delivered": {}}
    except (json.JSONDecodeError, OSError):
        return {"delivered": {}}
    if not isinstance(data, dict):
        return {"delivered": {}}
    delivered = data.get("delivered")
    if not isinstance(delivered, dict):
        data["delivered"] = {}
    return data


def save_delivery_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def mark_delivered(
    state: dict[str, Any],
    run: CronRun,
    payload: dict[str, Any],
    delivered_at: str | None = None,
) -> None:
    delivered = state.setdefault("delivered", {})
    if not isinstance(delivered, dict):
        delivered = {}
        state["delivered"] = delivered
    delivered[run.delivery_key] = {
        "delivered_at": delivered_at or now_iso(),
        "job_id": run.job_id,
        "display_text": payload.get("display_text", ""),
    }


def already_delivered(state: dict[str, Any], run: CronRun) -> bool:
    delivered = state.get("delivered")
    return isinstance(delivered, dict) and run.delivery_key in delivered


def _json_object_from_summary(summary: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(summary)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def reminder_payload_from_summary(summary: str) -> dict[str, Any] | None:
    payload = _json_object_from_summary(summary)
    if payload is None:
        return None

    payload_type = payload.get("type")
    metadata = payload.get("metadata")
    metadata_type = metadata.get("type") if isinstance(metadata, dict) else None
    display_text = payload.get("display_text")
    is_reminder = payload_type == "reminder.due" or metadata_type == "reminder.due" or (
        isinstance(display_text, str) and display_text.startswith("提醒：")
    )
    if not is_reminder:
        return None

    result = dict(payload)
    if not isinstance(result.get("type"), str) or not result.get("type"):
        result["type"] = metadata_type if isinstance(metadata_type, str) else "reminder.due"

    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    else:
        metadata = dict(metadata)
    metadata["source"] = BRIDGE_SOURCE
    result["metadata"] = metadata
    return result


def should_consider_run(run: CronRun, agent_id: str) -> bool:
    if run.status != "ok":
        return False
    if not run.summary:
        return False
    if run.session_key and f"agent:{agent_id}:" in run.session_key:
        return True
    payload = reminder_payload_from_summary(run.summary)
    return payload is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def fetch_completed_cron_runs(
    sqlite_path: Path,
    agent_id: str,
    lookback_seconds: int | None = DEFAULT_LOOKBACK_SECONDS,
) -> list[CronRun]:
    if not sqlite_path.exists():
        return []

    try:
        conn = sqlite3.connect(str(sqlite_path))
    except sqlite3.Error:
        return []

    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "cron_run_logs" not in tables:
            return []
        columns = _table_columns(conn, "cron_run_logs")
        required = {"job_id", "status", "summary"}
        if not required.issubset(columns):
            return []

        select_columns = [
            "job_id",
            "seq" if "seq" in columns else "NULL AS seq",
            "ts" if "ts" in columns else "NULL AS ts",
            "status",
            "summary",
            "run_id" if "run_id" in columns else "NULL AS run_id",
            "run_at_ms" if "run_at_ms" in columns else "NULL AS run_at_ms",
            "session_key" if "session_key" in columns else "NULL AS session_key",
            "entry_json" if "entry_json" in columns else "NULL AS entry_json",
        ]
        query = f"""
            SELECT {", ".join(select_columns)}
            FROM cron_run_logs
            WHERE status = 'ok'
        """
        params: list[Any] = []
        if lookback_seconds and "ts" in columns:
            query += " AND ts >= ?"
            params.append(int(time.time() * 1000) - int(lookback_seconds * 1000))
        query += " ORDER BY COALESCE(ts, run_at_ms, 0) ASC"

        runs = []
        for row in conn.execute(query, params).fetchall():
            run = CronRun(
                job_id=str(row[0]),
                seq=row[1],
                ts=row[2],
                status=str(row[3] or ""),
                summary=str(row[4] or ""),
                run_id=row[5],
                run_at_ms=row[6],
                session_key=row[7],
                entry_json=row[8],
            )
            if should_consider_run(run, agent_id):
                runs.append(run)
        return runs
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def post_notify(url: str, payload: dict[str, Any], timeout: float = 10.0) -> bool:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status < 200 or response.status >= 300:
                return False
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return False

    if not raw:
        return True
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return True
    if isinstance(data, dict) and data.get("ok") is False:
        return False
    return True


def deliver_runs_once(
    sqlite_path: Path,
    notify_url: str,
    state_file: Path,
    agent_id: str,
    lookback_seconds: int | None = DEFAULT_LOOKBACK_SECONDS,
    verbose: bool = False,
) -> int:
    state = load_delivery_state(state_file)
    runs = fetch_completed_cron_runs(sqlite_path, agent_id, lookback_seconds)
    delivered_count = 0

    if verbose:
        print(f"[bridge] scanned {len(runs)} candidate cron run(s)")

    for run in runs:
        if already_delivered(state, run):
            if verbose:
                print(f"[bridge] skip delivered {run.delivery_key}")
            continue
        payload = reminder_payload_from_summary(run.summary)
        if payload is None:
            if verbose:
                print(f"[bridge] skip non-reminder {run.delivery_key}")
            continue
        metadata = dict(payload.get("metadata") or {})
        cron_meta = dict(metadata.get("openclaw_cron") or {})
        cron_meta.update(
            {
                "job_id": run.job_id,
                "run_id": run.run_id,
                "run_at_ms": run.run_at_ms,
                "seq": run.seq,
            }
        )
        metadata["openclaw_cron"] = {
            key: value for key, value in cron_meta.items() if value is not None
        }
        metadata["source"] = BRIDGE_SOURCE
        payload["metadata"] = metadata

        if verbose:
            print(
                "[bridge] deliver "
                f"{run.delivery_key}: {payload.get('display_text', '')}"
            )
        if not post_notify(notify_url, payload):
            if verbose:
                print(f"[bridge] warning: notify POST failed for {run.delivery_key}")
            continue
        mark_delivered(state, run, payload)
        save_delivery_state(state_file, state)
        delivered_count += 1
    return delivered_count


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", type=Path, default=DEFAULT_SQLITE_PATH)
    parser.add_argument("--notify-url", default=DEFAULT_NOTIFY_URL)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument(
        "--lookback-seconds",
        type=int,
        default=DEFAULT_LOOKBACK_SECONDS,
        help="Only scan recent cron runs; set 0 to scan all history.",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    lookback_seconds = args.lookback_seconds if args.lookback_seconds > 0 else None

    while True:
        try:
            delivered = deliver_runs_once(
                sqlite_path=args.sqlite_path.expanduser(),
                notify_url=args.notify_url,
                state_file=args.state_file.expanduser(),
                agent_id=args.agent_id,
                lookback_seconds=lookback_seconds,
                verbose=args.verbose,
            )
            if args.verbose:
                print(f"[bridge] delivered {delivered} run(s)")
        except Exception as exc:  # pragma: no cover - last-resort loop guard
            print(f"[bridge] warning: {exc}", file=sys.stderr)

        if args.once:
            return 0
        time.sleep(max(0.5, args.poll_interval))


if __name__ == "__main__":
    raise SystemExit(main())
