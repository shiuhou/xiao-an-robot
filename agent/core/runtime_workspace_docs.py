"""Markdown-backed XiaoAn runtime workspace document helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid


DEFAULT_RUNTIME_WORKSPACE = Path.home() / ".openclaw" / "workspace-xiaoan-runtime"


@dataclass(frozen=True)
class WorkspaceWrite:
    ok: bool
    path: str
    section: str
    title: str
    error: str | None = None


class RuntimeWorkspaceDocs:
    """Append and query the runtime brain's small Markdown databases."""

    def __init__(self, workspace: str | Path | None = None):
        self.workspace = Path(
            workspace
            or os.environ.get("XIAOAN_RUNTIME_WORKSPACE")
            or DEFAULT_RUNTIME_WORKSPACE
        ).expanduser()

    @property
    def tasks_path(self) -> Path:
        return self.workspace / "TASKS.md"

    @property
    def schedule_path(self) -> Path:
        return self.workspace / "SCHEDULE.md"

    @property
    def dashboard_path(self) -> Path:
        return self.workspace / "state" / "dashboard.json"

    @property
    def local_reminders_path(self) -> Path:
        return self.workspace / "state" / "local_reminders.json"

    def add_task(
        self,
        title: str,
        *,
        transcript: str,
        run_id: str,
        due_date: str | None = None,
        now: datetime | None = None,
    ) -> WorkspaceWrite:
        timestamp = _now(now)
        due_line = f"\n  - due: {due_date}" if due_date else ""
        entry = (
            f"- [ ] {title.strip() or '未命名待办'}"
            f"{due_line}\n"
            f"  - source: local_fast_path / {run_id}\n"
            f"  - captured_at: {timestamp.isoformat()}\n"
            f"  - transcript: {transcript.strip()}\n"
        )
        return self._append_to_section(self.tasks_path, "## Today", entry, title.strip() or "未命名待办")

    def complete_task(self, query: str, *, transcript: str, run_id: str) -> WorkspaceWrite:
        return self._update_task_checkbox(
            query,
            checked=True,
            transcript=transcript,
            run_id=run_id,
            action="completed",
        )

    def cancel_task(self, query: str, *, transcript: str, run_id: str) -> WorkspaceWrite:
        return self._update_task_checkbox(
            query,
            checked=True,
            transcript=transcript,
            run_id=run_id,
            action="cancelled",
        )

    def add_schedule(
        self,
        title: str,
        *,
        transcript: str,
        run_id: str,
        due_at: str,
        kind: str = "schedule",
        now: datetime | None = None,
    ) -> WorkspaceWrite:
        del now
        date_text, time_text = _date_time_from_iso(due_at)
        label = "reminder" if kind == "reminder" else "schedule"
        suffix = (
            f"（pending，scheduler: local，id: {run_id}，来源：local_fast_path，session: {run_id}）"
            if label == "reminder"
            else f"（{label}，来源：local_fast_path，session: {run_id}）"
        )
        entry = f"- {date_text} {time_text} {title.strip() or transcript.strip() or '未命名事项'}{suffix}\n"
        section = "## Reminders" if label == "reminder" else "## Upcoming"
        return self._append_to_section(
            self.schedule_path,
            section,
            entry,
            title.strip() or transcript.strip() or "未命名事项",
        )

    def add_local_reminder(
        self,
        title: str,
        *,
        transcript: str,
        run_id: str,
        due_at: str,
        now: datetime | None = None,
    ) -> WorkspaceWrite:
        timestamp = _now(now).isoformat()
        reminder_id = run_id or f"local-{uuid.uuid4().hex[:10]}"
        payload = self._load_local_reminders()
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        items.append({
            "id": reminder_id,
            "title": title.strip() or "这件事",
            "message": title.strip() or "这件事",
            "due_at": due_at,
            "status": "pending",
            "source": "local_fast_path",
            "run_id": run_id,
            "session": run_id,
            "captured_at": timestamp,
            "transcript": transcript.strip(),
            "send_to_robot": True,
            "allow_motion": False,
        })
        payload.update({
            "schema_version": "xiaoan.local_reminders.v1",
            "updated_at": timestamp,
            "items": items,
        })
        try:
            self._write_json_atomic(self.local_reminders_path, payload)
        except OSError as exc:
            return WorkspaceWrite(False, str(self.local_reminders_path), "local_reminders", title, str(exc))
        return WorkspaceWrite(True, str(self.local_reminders_path), "local_reminders", title.strip() or "这件事")

    def today_tasks(self, *, now: datetime | None = None, limit: int = 8) -> list[str]:
        del now
        return _extract_checkbox_items(_read_text(self.tasks_path), limit=limit)

    def today_schedule(self, *, now: datetime | None = None, limit: int = 8) -> list[str]:
        today = _now(now).date().isoformat()
        items = []
        for line in _read_text(self.schedule_path).splitlines():
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            if today not in stripped:
                continue
            items.append(stripped[2:])
            if len(items) >= limit:
                break
        return items

    def pending_reminders(self, *, limit: int = 8) -> list[str]:
        payload = self._load_local_reminders()
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        reminders: list[str] = []
        for item in items:
            if not isinstance(item, dict) or item.get("status") != "pending":
                continue
            due_at = str(item.get("due_at") or "")
            title = str(item.get("title") or item.get("message") or "这件事")
            reminders.append(f"{due_at[:16]} {title}".strip())
            if len(reminders) >= limit:
                break
        return reminders

    def cancel_reminder(self, query: str, *, transcript: str, run_id: str) -> WorkspaceWrite:
        payload = self._load_local_reminders()
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        needle = _normalize_for_match(query)
        if not needle:
            return WorkspaceWrite(False, str(self.local_reminders_path), "local_reminders", query, "empty_query")

        matched: dict[str, Any] | None = None
        for item in reversed(items):
            if not isinstance(item, dict) or item.get("status") != "pending":
                continue
            haystack = _normalize_for_match(
                " ".join(str(item.get(key) or "") for key in ("title", "message", "transcript"))
            )
            if needle in haystack or haystack in needle:
                matched = item
                break
        if matched is None:
            return WorkspaceWrite(False, str(self.local_reminders_path), "local_reminders", query, "not_found")

        matched["status"] = "cancelled"
        matched["cancelled_at"] = _now().isoformat()
        matched["cancelled_by"] = "local_fast_path"
        matched["cancel_transcript"] = transcript.strip()
        matched["cancel_run_id"] = run_id
        payload["updated_at"] = _now().isoformat()
        payload["items"] = items
        try:
            self._write_json_atomic(self.local_reminders_path, payload)
            self._append_to_section(
                self.schedule_path,
                "## Done",
                f"- {matched.get('due_at', '')[:16]} {matched.get('title') or query}（cancelled，scheduler: local，id: {matched.get('id')}，来源：local_fast_path，session: {run_id}）\n",
                str(matched.get("title") or query),
            )
        except OSError as exc:
            return WorkspaceWrite(False, str(self.local_reminders_path), "local_reminders", query, str(exc))
        return WorkspaceWrite(True, str(self.local_reminders_path), "local_reminders", str(matched.get("title") or query))

    def update_dashboard_snapshot(
        self,
        *,
        run_id: str,
        route: str,
        intent: str,
        transcript: str,
        reply: str,
        storage: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> WorkspaceWrite:
        timestamp = _now(now).isoformat()
        latest_reply = {
            "display_text": reply,
            "spoken_text": reply,
            "reply_text": reply,
            "source": "local_fast_path",
            "route": route,
            "intent": intent,
            "run_id": run_id,
            "updated_at": timestamp,
        }
        dashboard = self._load_dashboard()
        history = dashboard.get("local_fast_path_history")
        if not isinstance(history, list):
            history = []
        history.append({
            "run_id": run_id,
            "route": route,
            "intent": intent,
            "transcript": transcript.strip(),
            "reply": reply,
            "storage": storage or [],
            "actions": actions or [],
            "updated_at": timestamp,
        })
        dashboard.update({
            "schema": "xiaoan.dashboard.v1",
            "updated_at": timestamp,
            "mode": "work_mode",
            "status_text": reply,
            "latest_reply": latest_reply,
            "local_fast_path": {
                "last_run_id": run_id,
                "last_route": route,
                "last_intent": intent,
                "last_transcript": transcript.strip(),
                "storage": storage or [],
                "actions": actions or [],
                "updated_at": timestamp,
            },
            "local_fast_path_history": history[-20:],
        })
        try:
            self._write_json_atomic(self.dashboard_path, dashboard)
        except OSError as exc:
            return WorkspaceWrite(False, str(self.dashboard_path), "dashboard", intent, str(exc))
        return WorkspaceWrite(True, str(self.dashboard_path), "dashboard", intent)

    def _append_to_section(self, path: Path, section: str, entry: str, title: str) -> WorkspaceWrite:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(_default_doc(path.name), encoding="utf-8")
            text = path.read_text(encoding="utf-8")
            if section not in text:
                text = text.rstrip() + f"\n\n{section}\n"
            marker = section + "\n"
            index = text.index(marker) + len(marker)
            updated = text[:index] + "\n" + entry + text[index:]
            path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            return WorkspaceWrite(False, str(path), section, title, str(exc))
        return WorkspaceWrite(True, str(path), section, title)

    def _update_task_checkbox(
        self,
        query: str,
        *,
        checked: bool,
        transcript: str,
        run_id: str,
        action: str,
    ) -> WorkspaceWrite:
        try:
            text = _read_text(self.tasks_path)
            if not text:
                return WorkspaceWrite(False, str(self.tasks_path), "## Today", query, "not_found")
            needle = _normalize_for_match(query)
            if not needle:
                return WorkspaceWrite(False, str(self.tasks_path), "## Today", query, "empty_query")
            lines = text.splitlines()
            target_index: int | None = None
            for index, line in enumerate(lines):
                stripped = line.strip()
                if not (stripped.startswith("- [ ] ") or stripped.startswith("- [x] ")):
                    continue
                title = stripped[6:].strip()
                title_norm = _normalize_for_match(title)
                if needle in title_norm or title_norm in needle:
                    target_index = index
                    break
            if target_index is None:
                return WorkspaceWrite(False, str(self.tasks_path), "## Today", query, "not_found")
            prefix = "- [x] " if checked else "- [ ] "
            old_title = lines[target_index].strip()[6:].strip()
            lines[target_index] = prefix + old_title
            timestamp = _now().isoformat()
            insert_at = target_index + 1
            metadata = [
                f"  - {action}_at: {timestamp}",
                f"  - {action}_source: local_fast_path / {run_id}",
                f"  - {action}_transcript: {transcript.strip()}",
            ]
            for offset, line in enumerate(metadata):
                lines.insert(insert_at + offset, line)
            self.tasks_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        except OSError as exc:
            return WorkspaceWrite(False, str(self.tasks_path), "## Today", query, str(exc))
        return WorkspaceWrite(True, str(self.tasks_path), "## Today", old_title)

    def _load_dashboard(self) -> dict[str, Any]:
        data = _read_json(self.dashboard_path)
        if isinstance(data, dict):
            return data
        return {"schema": "xiaoan.dashboard.v1"}

    def _load_local_reminders(self) -> dict[str, Any]:
        data = _read_json(self.local_reminders_path)
        if isinstance(data, dict):
            data.setdefault("schema_version", "xiaoan.local_reminders.v1")
            if not isinstance(data.get("items"), list):
                data["items"] = []
            return data
        return {"schema_version": "xiaoan.local_reminders.v1", "updated_at": None, "items": []}

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)


def clean_capture_title(text: str, *, kind: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^\s*(小安[，,\s]*)+", "", value)
    replacements = [
        "帮我", "请", "把", "加个", "新增", "添加", "加入todo list", "加入待办", "加到待办",
        "添加待办", "待办", "任务", "加入日程", "加到日程", "添加日程",
        "日程", "提醒我", "提醒", "叫我一下", "叫我", "喊我", "通知我", "记得",
        "创建", "记录", "安排",
    ]
    for token in replacements:
        value = value.replace(token, "")
    if kind in {"schedule", "reminder"}:
        value = re.sub(r"(今天|明天|后天)?(早上|上午|中午|下午|晚上)?[一二两三四五六七八九十\d]{1,3}点(半|[一二两三四五六七八九十\d]{1,3}分?)?", "", value)
        value = re.sub(r"[一二两三四五六七八九十\d]+(秒钟?|分钟?|小时|钟头)(后|之后|以后)", "", value)
        value = re.sub(r"过[一二两三四五六七八九十\d]+(秒钟?|分钟?|小时|钟头)", "", value)
        value = value.replace("待会", "").replace("等会", "").replace("过会", "").replace("到点", "")
    value = value.strip(" ，。,.：:;；")
    return value or ("这件事" if kind == "reminder" else "未命名事项")


def _default_doc(name: str) -> str:
    if name == "TASKS.md":
        return "# TASKS.md - Tasks\n\n## Inbox\n\n## Today\n\n## Upcoming\n\n## Waiting\n\n## Done\n"
    if name == "SCHEDULE.md":
        return "# SCHEDULE.md - Schedule\n\n## Today\n\n## Upcoming\n\n## Reminders\n\n## Done\n"
    return f"# {name}\n"


def _now(now: datetime | None = None) -> datetime:
    active = now or datetime.now().astimezone()
    return active.astimezone() if active.tzinfo is not None else active


def _date_time_from_iso(value: str) -> tuple[str, str]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)[:10] or "日期待补充", str(value)[11:16] or "时间待补充"
    return parsed.date().isoformat(), parsed.strftime("%H:%M")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _extract_checkbox_items(text: str, *, limit: int) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- [ ] "):
            continue
        items.append(stripped[6:].strip())
        if len(items) >= limit:
            break
    return items


def _normalize_for_match(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or "").lower())
    for token in ("小安", "帮我", "请", "把", "这个", "那个", "一下", "取消", "完成", "查", "查询", "提醒", "待办", "任务"):
        text = text.replace(token, "")
    return text.strip("，。,.：:;；")
