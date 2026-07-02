"""One-task integration loop scheduler.

Each cycle selects at most one highest-priority READY task whose dependencies
are complete, then records the selection or command result in a JSON state file.
This keeps long-running integration work resumable without letting an agent
batch unrelated hardware tasks.
"""

from __future__ import annotations

import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any


PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
BLOCKING_STATUSES = {"WAITING_HUMAN", "RUNNING", "BLOCKED_RETRY", "NEEDS_FIX"}
DONE_STATUSES = {"PASS", "DONE", "COMPLETE", "COMPLETED"}
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE = ROOT / "docs" / "agents" / "08_priority_queue.yaml"
DEFAULT_STATE = ROOT / "docs" / "agents" / "08_priority_queue_results.json"


def _repo_relative_path(path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.exists() or resolved.is_absolute():
        return resolved
    repo_path = ROOT / resolved
    return repo_path if repo_path.exists() else resolved


def _coerce_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        return value.strip("\"'")


def _load_simple_queue_yaml(path: Path) -> dict[str, Any]:
    queue: dict[str, Any] = {"policy": {}, "tasks": []}
    section: str | None = None
    current_task: dict[str, Any] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if line == "policy:":
            section = "policy"
            continue
        if line == "tasks:":
            section = "tasks"
            continue
        if section == "policy" and line.startswith("  "):
            key, value = line.strip().split(":", 1)
            queue["policy"][key] = _coerce_scalar(value)
            continue
        if section == "tasks" and line.startswith("  - "):
            current_task = {}
            queue["tasks"].append(current_task)
            item = line[4:].strip()
            if item:
                key, value = item.split(":", 1)
                current_task[key] = _coerce_scalar(value)
            continue
        if section == "tasks" and current_task is not None and line.startswith("    "):
            key, value = line.strip().split(":", 1)
            current_task[key] = _coerce_scalar(value)
            continue
        raise ValueError(f"Unsupported queue YAML line: {raw_line}")

    return queue


def load_queue(path: str | Path) -> dict[str, Any]:
    queue_path = _repo_relative_path(path)
    text = queue_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        if not isinstance(data, dict):
            raise ValueError(f"Queue file must contain a mapping: {queue_path}")
        return data

    try:
        import yaml  # type: ignore
    except ImportError:
        return _load_simple_queue_yaml(queue_path)

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Queue file must contain a mapping: {queue_path}")
    return data


def _task_done(task_id: str, tasks_by_id: dict[str, dict[str, Any]], results: dict[str, Any]) -> bool:
    if task_id in results:
        result = results[task_id]
        if isinstance(result, dict):
            return str(result.get("status", "")).upper() in DONE_STATUSES
        return bool(result)
    task = tasks_by_id.get(task_id)
    return bool(task and str(task.get("status", "")).upper() in DONE_STATUSES)


def select_next_task(queue: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state or {}
    tasks = list(queue.get("tasks", []))
    tasks_by_id = {task["id"]: task for task in tasks}
    results = state.get("results", {})

    current = state.get("current_task")
    if current and str(current.get("status", "")).upper() in BLOCKING_STATUSES:
        task = tasks_by_id[current["task_id"]]
        max_attempts = int(queue.get("policy", {}).get("max_fix_attempts", 2))
        attempt = int(current.get("attempt", 0))
        if str(current.get("status", "")).upper() == "NEEDS_FIX" and attempt >= max_attempts:
            return {"task": task, "reason": "max_fix_attempts"}
        return {"task": task, "reason": "active_task"}

    ready: list[dict[str, Any]] = []
    for task in tasks:
        if _task_done(task["id"], tasks_by_id, results):
            continue
        if str(task.get("status", "")).upper() != "READY":
            continue
        dependencies = task.get("depends_on") or []
        if all(_task_done(dep, tasks_by_id, results) for dep in dependencies):
            ready.append(task)

    if not ready:
        return {"task": None, "reason": "no_ready_task"}

    ready.sort(key=lambda task: (PRIORITY_ORDER.get(str(task.get("priority", "P9")), 99), task["id"]))
    return {"task": ready[0], "reason": "ready"}


def load_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {"current_task": None, "results": {}, "history": []}
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"State file must contain a JSON object: {state_path}")
    data.setdefault("current_task", None)
    data.setdefault("results", {})
    data.setdefault("history", [])
    return data


def save_state(path: str | Path, state: dict[str, Any]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolve_cwd(cwd: str | None) -> Path:
    if not cwd or cwd == ".":
        return ROOT
    path = Path(cwd)
    return path if path.is_absolute() else ROOT / path


def _tail(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _run_task_command(task: dict[str, Any]) -> dict[str, Any]:
    command = task.get("command")
    if not command:
        return {
            "status": "WAITING_HUMAN",
            "returncode": None,
            "reason": "manual_task",
        }
    command_args = command.split() if isinstance(command, str) else list(command)
    completed = subprocess.run(
        command_args,
        cwd=_resolve_cwd(task.get("cwd")),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def run_cycle(
    queue_path: str | Path = DEFAULT_QUEUE,
    state_path: str | Path = DEFAULT_STATE,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    queue = load_queue(queue_path)
    state = load_state(state_path)
    selected = select_next_task(queue, state)
    selected_task = selected.get("task")
    cycle = {
        "at": _now(),
        "reason": selected["reason"],
        "task_id": selected_task.get("id") if selected_task else None,
        "execute": execute,
    }
    state["history"].append(cycle)

    if selected_task is None:
        save_state(state_path, state)
        return {"selected": selected, "state": state}

    previous = state["results"].get(selected_task["id"], {})
    previous_attempt = int(previous.get("attempt", 0)) if isinstance(previous, dict) else 0

    if not execute:
        state["current_task"] = {
            "task_id": selected_task["id"],
            "status": "WAITING_HUMAN",
            "attempt": previous_attempt,
            "selected_at": cycle["at"],
            "reason": selected["reason"],
        }
        save_state(state_path, state)
        return {"selected": selected, "state": state}

    state["current_task"] = {
        "task_id": selected_task["id"],
        "status": "RUNNING",
        "attempt": previous_attempt + 1,
        "started_at": cycle["at"],
    }
    save_state(state_path, state)

    result = _run_task_command(selected_task)
    finished_at = _now()
    status = result["status"]
    if status == "PASS":
        attempt = previous_attempt + 1
        current_status = "PASS"
    elif status == "WAITING_HUMAN":
        attempt = previous_attempt
        current_status = "WAITING_HUMAN"
    else:
        attempt = previous_attempt + 1
        max_attempts = int(queue.get("policy", {}).get("max_fix_attempts", 2))
        current_status = "NEEDS_FIX" if attempt < max_attempts else "BLOCKED_RETRY"

    state["results"][selected_task["id"]] = {
        **result,
        "attempt": attempt,
        "finished_at": finished_at,
        "title": selected_task.get("title", ""),
    }
    state["current_task"] = {
        "task_id": selected_task["id"],
        "status": current_status,
        "attempt": attempt,
        "finished_at": finished_at,
    }
    save_state(state_path, state)
    return {"selected": selected, "state": state}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Xiao An integration queue cycle.")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE), help="Priority queue YAML path.")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="JSON results/state path.")
    parser.add_argument("--execute", action="store_true", help="Execute the selected task command.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_cycle(args.queue, args.state, execute=args.execute)
    print(json.dumps(result["selected"], ensure_ascii=False, indent=2))
    return 1 if result["selected"]["reason"] == "max_fix_attempts" else 0


if __name__ == "__main__":
    raise SystemExit(main())
