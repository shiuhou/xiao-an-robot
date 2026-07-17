"""Shared object container for the local HTTP API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from agent.core.action_executor import ActionExecutor
from agent.core.brain import XiaoAnBrain
from agent.core.context_builder import ContextBuilder
from agent.core.gateway import RobotGateway
from agent.core.local_tools import LocalToolRegistry
from agent.core.memory import XiaoAnMemoryStore
from agent.core.openclaw_adapter import (
    FakeOpenClawAdapter,
    OpenClawDecision,
    OpenClawToolCall,
)
from agent.core.openclaw_adapter_factory import build_openclaw_adapter_from_env
from agent.core.project_memory import ProjectMemoryService
from agent.core.xiaoan_tool_manifest import tool_manifest
from agent.skills.robot_motion import RobotMotionSkill
from base_station.monitor.emotion_db import EmotionDB


OPENCLAW_OWNED_FEATURES = [
    "user_profile",
    "long_term_memory",
    "scheduled_reminders",
    "tasks",
    "morning_brief",
    "daily_report",
    "natural_language_replies",
    "tool_selection",
]

XIAO_AN_ROBOT_OWNED_FEATURES = [
    "robot_body",
    "perception_pipeline",
    "local_emotion_thresholds",
    "safety_policy",
    "esp32_communication",
    "robot_action_execution",
    "local_event_store",
]

DEPRECATED_LOCAL_FEATURES = [
    {
        "name": "reminders",
        "status": "legacy_compatibility",
        "replacement_owner": "openclaw_xiaoan_runtime",
    },
    {
        "name": "tasks",
        "status": "legacy_compatibility",
        "replacement_owner": "openclaw_xiaoan_runtime",
    },
    {
        "name": "notes",
        "status": "legacy_compatibility",
        "replacement_owner": "openclaw_xiaoan_runtime",
    },
    {
        "name": "summaries",
        "status": "legacy_compatibility",
        "replacement_owner": "openclaw_xiaoan_runtime",
    },
    {
        "name": "work_activity",
        "status": "legacy_compatibility",
        "replacement_owner": "openclaw_xiaoan_runtime",
    },
    {
        "name": "screen_monitoring",
        "status": "deprecated",
        "replacement_owner": None,
    },
]

DEFAULT_OPENCLAW_WORKSPACE = Path.home() / ".openclaw" / "workspace-xiaoan-runtime"
OPENCLAW_DASHBOARD_SCHEMA = "xiaoan.dashboard.v1"


def build_api_openclaw_adapter(environ: dict[str, str] | None = None) -> Any:
    active_environ = os.environ if environ is None else environ
    backend = active_environ.get("XIAO_AN_OPENCLAW_BACKEND", "fake").strip().lower()
    if backend in {"", "fake"}:
        return FakeOpenClawAdapter(decision=OpenClawDecision(handled=False))
    return build_openclaw_adapter_from_env(active_environ)


class ApiRuntime:
    """Own the lightweight services shared by API requests."""

    def __init__(
        self,
        db_path: str = "agent/data/xiao_an.db",
        robot_ws_url: str = "ws://127.0.0.1:8765/agent",
        openclaw_workspace: str | Path | None = None,
        verbose: bool = False,
    ):
        self.db_path = str(Path(db_path))
        self.robot_ws_url = robot_ws_url
        self.openclaw_workspace = Path(
            openclaw_workspace or DEFAULT_OPENCLAW_WORKSPACE
        ).expanduser()
        self.openclaw_dashboard_path = (
            self.openclaw_workspace / "state" / "dashboard.json"
        )
        self.verbose = bool(verbose)
        self.closed = False
        self._operation_lock = threading.RLock()
        self.robot_connection_status = "unknown_until_command_ack"
        self.robot_connection_detail: dict[str, Any] = {
            "last_checked_by": None,
            "last_tool": None,
            "last_device_id": None,
            "last_forwarded_type": None,
            "latest_command_ack": None,
            "last_error": None,
        }
        self._latest_reply: dict[str, Any] | None = None

        self.memory_store = XiaoAnMemoryStore(
            db_path=self.db_path,
            check_same_thread=False,
        )
        self.project_memory = ProjectMemoryService(
            memory_store=self.memory_store,
        )
        self.local_tools = LocalToolRegistry(
            memory_store=self.memory_store,
            project_memory_service=self.project_memory,
        )
        self.robot_gateway = RobotGateway(url=self.robot_ws_url)
        self.robot_motion = RobotMotionSkill(gateway=self.robot_gateway)
        self.emotion_memory = EmotionDB(
            db_path=self.db_path,
            check_same_thread=False,
        )
        self.action_executor = ActionExecutor(
            robot_motion_skill=self.robot_motion,
            local_tool_registry=self.local_tools,
            memory_store=self.memory_store,
            project_memory_service=self.project_memory,
            emotion_snapshot_provider=self.emotion_memory.get_recent_summary,
            runtime_status_provider=self.status,
        )
        self.context_builder = ContextBuilder(memory_store=self.memory_store)
        self.brain = XiaoAnBrain(
            gateway=self.robot_gateway,
            memory=self.emotion_memory,
            gateway_url=self.robot_ws_url,
            db_path=self.db_path,
            openclaw_adapter=build_api_openclaw_adapter(),
            action_executor=self.action_executor,
            context_builder=self.context_builder,
            context_memory=self.memory_store,
        )

    def chat(
        self,
        text: str,
        session_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "type": "frontend.message",
            "payload": {
                "text": text,
                "session_id": session_id,
                "metadata": dict(metadata or {}),
            },
        }
        with self._operation_lock:
            result = self.run_async(self.brain.handle_event(event))
            if isinstance(result, dict):
                display_text = self._text_or_empty(result.get("display_text", ""))
                spoken_text = self._text_or_empty(result.get("spoken_text", ""))
                reply_text = self._text_or_empty(result.get("reply_text", ""))
            else:
                display_text = ""
                spoken_text = ""
                reply_text = ""
            if display_text or spoken_text or reply_text:
                self._set_latest_reply(
                    notification_type="frontend.message",
                    display_text=display_text or reply_text,
                    spoken_text=spoken_text,
                    reply_text=reply_text,
                tool_calls=[],
                metadata=dict(metadata or {}),
                session_id=session_id,
                source="api.chat",
                suppress_auto_tts=False,
                execution_result=result,
            )
            return result

    def preview_context(
        self,
        text: str,
        session_id: str = "default",
    ) -> dict[str, Any]:
        payload = {
            "text": text,
            "session_id": session_id,
        }
        with self._operation_lock:
            context = self.context_builder.build_for_text(
                text,
                base_context={"payload": payload},
                event_type="frontend.message",
                source="frontend",
            )
        context_policy = context.get("context_policy", {})
        return {
            "text": text,
            "session_id": session_id,
            "requested_scopes": list(
                context_policy.get("requested_scopes", []),
            ),
            "context": context,
        }

    def list_tools(self) -> dict[str, Any]:
        return {
            "tools": tool_manifest(),
            "legacy_tools": [
                {"name": name, "status": "legacy_compatibility"}
                for name in sorted(
                    set(self.action_executor.LEGACY_ROBOT_TOOL_ALIASES)
                    | self.action_executor.LOCAL_TOOL_NAMES
                )
            ],
        }

    def latest_reply(self) -> dict[str, Any]:
        with self._operation_lock:
            latest = self._latest_reply
            if latest is None:
                return {
                    "available": False,
                    "latest": None,
                }
            return {
                "available": True,
                "latest": self._copy_jsonish(latest),
            }

    def notify_from_openclaw(
        self,
        notification_type: str,
        display_text: str = "",
        spoken_text: str = "",
        reply_text: str = "",
        suppress_auto_tts: bool = False,
        tool_calls: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str = "default",
    ) -> dict[str, Any]:
        parsed_tool_calls = [
            OpenClawToolCall.from_dict(item)
            for item in (tool_calls or [])
            if isinstance(item, dict)
        ]
        active_display_text = self._text_or_empty(display_text)
        active_spoken_text = self._text_or_empty(spoken_text)
        active_reply_text = self._text_or_empty(reply_text)
        active_metadata = dict(metadata or {})
        tool_call_payloads = [
            tool_call.to_dict()
            for tool_call in parsed_tool_calls
        ]
        raw_notification = {
            "type": notification_type,
            "display_text": active_display_text,
            "spoken_text": active_spoken_text,
            "reply_text": active_reply_text,
            "suppress_auto_tts": bool(suppress_auto_tts),
            "tool_calls": tool_call_payloads,
            "metadata": active_metadata,
            "session_id": session_id,
        }
        decision = OpenClawDecision(
            handled=True,
            display_text=active_display_text,
            spoken_text=active_spoken_text,
            reply_text=active_reply_text,
            suppress_auto_tts=bool(suppress_auto_tts),
            tool_calls=parsed_tool_calls,
            raw={
                "source": "api.openclaw.notify",
                "notification": raw_notification,
            },
        )

        with self._operation_lock:
            execution_result = self.run_async(
                self.action_executor.execute(
                    decision,
                    source_event_type="api.openclaw.notify",
                ),
            )
            for tool_call in parsed_tool_calls:
                self._update_robot_connection_status(
                    tool_call.name,
                    execution_result,
                )
            latest = self._set_latest_reply(
                notification_type=notification_type,
                display_text=active_display_text,
                spoken_text=active_spoken_text,
                reply_text=active_reply_text,
                tool_calls=tool_call_payloads,
                metadata=active_metadata,
                session_id=session_id,
                source="api.openclaw.notify",
                suppress_auto_tts=bool(suppress_auto_tts),
                execution_result=execution_result,
            )

        return {
            "notification": raw_notification,
            "latest": latest,
            "execution_result": execution_result,
        }

    def call_tool(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        session_id: str = "default",
        source_event_type: str = "api.tools.call",
    ) -> dict[str, Any]:
        active_arguments = dict(arguments or {})
        active_arguments.setdefault("session_id", session_id)
        decision = OpenClawDecision(
            handled=True,
            tool_calls=[
                OpenClawToolCall(
                    name=tool,
                    arguments=active_arguments,
                ),
            ],
        )
        with self._operation_lock:
            result = self.run_async(
                self.action_executor.execute(
                    decision,
                    source_event_type=source_event_type,
                ),
            )
            self._update_robot_connection_status(tool, result)
        return {
            "tool": tool,
            "session_id": session_id,
            "result": result,
        }

    def create_task(
        self,
        arguments: dict[str, Any],
        session_id: str = "default",
    ) -> dict[str, Any]:
        return self.call_tool(
            "task.add",
            arguments=arguments,
            session_id=session_id,
            source_event_type="api.tasks.create",
        )

    def complete_task(
        self,
        task_id: int,
        session_id: str = "default",
    ) -> dict[str, Any]:
        return self.call_tool(
            "task.complete",
            arguments={"task_id": int(task_id)},
            session_id=session_id,
            source_event_type="api.tasks.complete",
        )

    def cancel_task(
        self,
        task_id: int,
        session_id: str = "default",
    ) -> dict[str, Any]:
        return self.call_tool(
            "task.cancel",
            arguments={"task_id": int(task_id)},
            session_id=session_id,
            source_event_type="api.tasks.cancel",
        )

    def create_reminder(
        self,
        arguments: dict[str, Any],
        session_id: str = "default",
    ) -> dict[str, Any]:
        return self.call_tool(
            "reminder.add",
            arguments=arguments,
            session_id=session_id,
            source_event_type="api.reminders.create",
        )

    def cancel_reminder(
        self,
        reminder_id: int,
        session_id: str = "default",
    ) -> dict[str, Any]:
        return self.call_tool(
            "reminder.cancel",
            arguments={"reminder_id": int(reminder_id)},
            session_id=session_id,
            source_event_type="api.reminders.cancel",
        )

    def get_due_reminders(
        self,
        now_ms: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        with self._operation_lock:
            reminders = self.memory_store.query_due_reminders(
                now_ms=now_ms,
                limit=limit,
            )
        return {
            "reminders": reminders,
            "items": reminders,
            "count": len(reminders),
        }

    def mark_reminder_fired(
        self,
        reminder_id: int,
        fired_at_ms: int | None = None,
        session_id: str = "default",
    ) -> dict[str, Any]:
        arguments = {
            "reminder_id": int(reminder_id),
            "fired_at_ms": fired_at_ms,
        }
        with self._operation_lock:
            result = self.memory_store.mark_reminder_fired(
                reminder_id=int(reminder_id),
                fired_at_ms=fired_at_ms,
                source="api",
            )
            ok = bool(result.get("ok", False))
            self.project_memory.record_tool_run(
                tool_name="reminder.mark_fired",
                arguments=arguments,
                result=result,
                ok=ok,
                source="api",
                source_event_type="api.reminders.mark-fired",
                session_id=session_id,
                error=None if ok else "reminder_not_found",
            )
        return result

    def query_recent_memory(
        self,
        limit: int = 20,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        with self._operation_lock:
            events = self.memory_store.query_recent_events(
                limit=limit,
                event_type=event_type,
            )
        return {"events": events, "items": events, "count": len(events)}

    def query_notes(
        self,
        keyword: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        with self._operation_lock:
            notes = self.project_memory.search_notes(
                keyword=keyword,
                limit=limit,
            )
        return {"notes": notes, "items": notes, "count": len(notes)}

    def query_work_activities(
        self,
        keyword: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        with self._operation_lock:
            activities = self.project_memory.query_work_activities(
                keyword=keyword,
                limit=limit,
            )
        return {
            "work_activities": activities,
            "items": activities,
            "count": len(activities),
        }

    def ingest_work_activity(
        self,
        arguments: dict[str, Any],
        session_id: str = "default",
    ) -> dict[str, Any]:
        """Persist one screen-derived work activity (PC client -> Local Event Store).

        A pure Local-Event-Store write: it records the row and returns, with NO
        dispatch into the response pipeline, so ingesting activity never makes the
        robot speak or act. The one-line gist rides in `note` and reaches OpenClaw
        only when the user later asks for help (via ContextBuilder at ask-time)."""
        args = dict(arguments or {})

        raw_conf = args.get("confidence")
        try:
            confidence = float(raw_conf) if raw_conf is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0

        raw_dur = args.get("duration_seconds")
        try:
            duration_seconds = float(raw_dur) if raw_dur is not None else None
        except (TypeError, ValueError):
            duration_seconds = None

        raw_ts = args.get("timestamp_ms")
        try:
            timestamp_ms = int(raw_ts) if raw_ts is not None else None
        except (TypeError, ValueError):
            timestamp_ms = None

        raw_pid = args.get("project_id")
        project_id = raw_pid if isinstance(raw_pid, int) and not isinstance(raw_pid, bool) else None

        with self._operation_lock:
            result = self.memory_store.insert_work_activity(
                source=str(args.get("source") or "screen"),
                app_name=str(args.get("app_name") or ""),
                window_title=str(args.get("window_title") or ""),
                activity_type=str(args.get("activity_type") or "unknown"),
                project_hint=args.get("project_hint"),
                note=args.get("note"),
                confidence=confidence,
                duration_seconds=duration_seconds,
                timestamp_ms=timestamp_ms,
                project_id=project_id,
                session_id=session_id,
            )
        return {
            "work_activity": result,
            "event_id": result.get("event_id"),
            "work_activity_id": result.get("work_activity_id"),
        }

    def query_summaries(
        self,
        summary_type: str | None = None,
        date: str | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        with self._operation_lock:
            summaries = self.project_memory.query_summaries(
                summary_type=summary_type,
                date=date,
                keyword=keyword,
                limit=limit,
            )
        return {
            "summaries": summaries,
            "items": summaries,
            "count": len(summaries),
        }

    def query_tool_runs(
        self,
        tool_name: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        with self._operation_lock:
            runs = self.memory_store.query_recent_tool_runs(
                limit=limit,
                tool_name=tool_name,
                status=status,
            )
        return {"tool_runs": runs, "items": runs, "count": len(runs)}

    def query_tasks(
        self,
        status: str | None = None,
        include_done: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        with self._operation_lock:
            tasks = self.project_memory.query_tasks(
                limit=limit,
                status=status,
                include_done=include_done,
            )
        return {"tasks": tasks, "items": tasks, "count": len(tasks)}

    def query_reminders(
        self,
        status: str | None = None,
        include_fired: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        with self._operation_lock:
            reminders = self.project_memory.query_reminders(
                limit=limit,
                status=status,
                include_fired=include_fired,
            )
        return {
            "reminders": reminders,
            "items": reminders,
            "count": len(reminders),
        }

    def query_project_context(
        self,
        scope: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        with self._operation_lock:
            return self.project_memory.get_recent_project_context(
                scope=scope,
                limit=limit,
            )

    def run_async(self, awaitable: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)

        result: list[Any] = []
        errors: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(awaitable))
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if errors:
            raise errors[0]
        return result[0] if result else None

    def status(self) -> dict[str, Any]:
        components = {
            "memory_store": self.memory_store is not None,
            "project_memory": self.project_memory is not None,
            "local_tools": self.local_tools is not None,
            "action_executor": self.action_executor is not None,
            "context_builder": self.context_builder is not None,
            "robot_gateway": self.robot_gateway is not None,
            "robot_motion": self.robot_motion is not None,
            "brain": self.brain is not None,
        }
        openclaw_backend = os.environ.get("XIAO_AN_OPENCLAW_BACKEND", "fake").strip() or "fake"
        return {
            "service": "xiao-an-local-api",
            "status": "closed" if self.closed else "ready",
            "db_path": self.db_path,
            "storage_role": "local_event_store",
            "robot_ws_url": self.robot_ws_url,
            "robot_connection_status": self.robot_connection_status,
            "robot_connection_detail": dict(self.robot_connection_detail),
            "openclaw_backend": openclaw_backend,
            "openclaw_gateway_url": os.environ.get("XIAO_AN_OPENCLAW_GATEWAY_URL", ""),
            "openclaw_agent": os.environ.get("XIAO_AN_OPENCLAW_AGENT", "xiaoan-runtime"),
            "verbose": self.verbose,
            "components": components,
            "openclaw_owned_features": list(OPENCLAW_OWNED_FEATURES),
            "xiao_an_robot_owned_features": list(XIAO_AN_ROBOT_OWNED_FEATURES),
            "deprecated_local_features": [
                dict(feature)
                for feature in DEPRECATED_LOCAL_FEATURES
            ],
        }

    def close(self) -> None:
        if self.closed:
            return
        with self._operation_lock:
            self.closed = True
            self._safe_close(self.brain)
            self._safe_close(self.project_memory)
            self._safe_close(self.memory_store)

    def _update_robot_connection_status(
        self,
        tool: str,
        action_result: dict[str, Any],
    ) -> None:
        if not tool.startswith("xiaoan.robot."):
            return

        executed_actions = action_result.get("executed_actions", [])
        skipped_actions = action_result.get("skipped_actions", [])
        detail = {
            "last_checked_by": "api.tools.call",
            "last_tool": tool,
            "last_device_id": None,
            "last_forwarded_type": None,
            "latest_command_ack": None,
            "last_error": None,
        }

        for action in executed_actions:
            result = action.get("result", {})
            for payload in self._iter_robot_ack_payloads(result):
                detail["last_device_id"] = payload.get("device_id")
                detail["last_forwarded_type"] = payload.get("forwarded_type")
                detail["latest_command_ack"] = dict(payload)
            self.robot_connection_status = "online_via_command_ack"
            self.robot_connection_detail = detail
            return

        if skipped_actions:
            result = skipped_actions[0].get("result", {})
            error = result.get("error") if isinstance(result, dict) else None
            detail["last_error"] = error or skipped_actions[0].get("reason")
            self.robot_connection_status = "offline_via_command_ack"
            self.robot_connection_detail = detail

    def _set_latest_reply(
        self,
        notification_type: str,
        display_text: str,
        spoken_text: str,
        reply_text: str,
        tool_calls: list[dict[str, Any]],
        metadata: dict[str, Any],
        session_id: str,
        source: str,
        suppress_auto_tts: bool = False,
        execution_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        output_text = (
            self._text_or_empty(display_text)
            or self._text_or_empty(spoken_text)
            or self._text_or_empty(reply_text)
            or self._first_say_text(tool_calls)
        )
        latest = {
            "type": notification_type,
            "display_text": self._text_or_empty(display_text),
            "spoken_text": self._text_or_empty(spoken_text),
            "reply_text": self._text_or_empty(reply_text),
            "suppress_auto_tts": bool(suppress_auto_tts),
            "output_text": output_text,
            "tool_calls": self._copy_jsonish(tool_calls),
            "metadata": self._copy_jsonish(metadata),
            "session_id": session_id,
            "source": source,
            "received_at_ms": int(time.time() * 1000),
        }
        if execution_result is not None:
            latest["execution_result"] = self._copy_jsonish(execution_result)
        self._latest_reply = latest
        try:
            self._sync_latest_reply_to_dashboard(latest)
        except Exception as exc:
            if self.verbose:
                print(f"warning: failed to sync latest reply to dashboard: {exc}")
        return self._copy_jsonish(latest)

    def _sync_latest_reply_to_dashboard(self, latest: dict[str, Any]) -> None:
        now_iso = self._now_iso()
        dashboard = self._load_dashboard_snapshot()
        status_text = (
            self._text_or_empty(latest.get("display_text", ""))
            or self._text_or_empty(latest.get("output_text", ""))
            or self._text_or_empty(latest.get("reply_text", ""))
            or self._text_or_empty(dashboard.get("status_text", ""))
        )

        dashboard["schema"] = OPENCLAW_DASHBOARD_SCHEMA
        dashboard["updated_at"] = now_iso
        dashboard["mode"] = self._dashboard_mode_for_latest(latest, dashboard)
        dashboard["status_text"] = status_text
        dashboard["next_item"] = dashboard.get("next_item")
        dashboard["todos"] = self._list_or_empty(dashboard.get("todos"))
        dashboard["schedules"] = self._list_or_empty(dashboard.get("schedules"))
        dashboard["reminders"] = self._list_or_empty(dashboard.get("reminders"))
        capture_item = self._dashboard_item_for_latest_capture(latest, now_iso)
        if capture_item is not None:
            list_name, item = capture_item
            dashboard[list_name] = self._upsert_dashboard_item(
                dashboard[list_name],
                item,
            )
            dashboard["next_item"] = item
        dashboard["latest_reply"] = {
            "display_text": self._text_or_empty(latest.get("display_text", "")),
            "spoken_text": self._text_or_empty(latest.get("spoken_text", "")),
            "source": self._text_or_empty(latest.get("source", "")),
            "received_at": now_iso,
        }

        self.openclaw_dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.openclaw_dashboard_path.with_name(
            f"{self.openclaw_dashboard_path.name}.tmp"
        )
        tmp_path.write_text(
            json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.openclaw_dashboard_path)

    def _dashboard_item_for_latest_capture(
        self,
        latest: dict[str, Any],
        timestamp: str,
    ) -> tuple[str, dict[str, Any]] | None:
        capture = self._extract_openclaw_capture(latest)
        if capture is None:
            return None
        if self._text_or_empty(capture.get("status", "")).lower() != "captured":
            return None

        kind = self._text_or_empty(capture.get("kind", "")).lower()
        list_name = {
            "task": "todos",
            "todo": "todos",
            "note": "todos",
            "idea": "todos",
            "schedule": "schedules",
            "meeting": "schedules",
            "reminder": "reminders",
            "alarm": "reminders",
        }.get(kind)
        if list_name is None:
            return None

        transcript = self._dashboard_capture_transcript(latest)
        title = (
            self._text_or_empty(capture.get("title", ""))
            or self._text_or_empty(capture.get("content", ""))
            or self._text_or_empty(latest.get("display_text", ""))
            or transcript
            or "语音事项"
        )
        content = self._text_or_empty(capture.get("content", ""))
        fingerprint = "|".join([
            kind,
            title,
            content,
            transcript,
            self._text_or_empty(latest.get("session_id", "")),
        ])
        item = {
            "id": "openclaw-capture-"
            + hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12],
            "title": title,
            "status": "pending",
            "source": "openclaw_capture",
            "runtime_source": self._text_or_empty(latest.get("source", "")),
            "created_at": timestamp,
            "transcript": transcript,
        }

        if list_name == "todos":
            item["type"] = "todo"
            item["priority"] = self._text_or_empty(capture.get("priority", "")) or "normal"
            due_text = (
                self._text_or_empty(capture.get("due_text", ""))
                or self._text_or_empty(capture.get("due_date", ""))
                or self._text_or_empty(capture.get("due_at", ""))
            )
            if due_text:
                item["due_text"] = due_text
            if kind in {"note", "idea"} and not due_text:
                item["due_text"] = "语音笔记"
        elif list_name == "schedules":
            fallback_due_at = self._datetime_from_capture_text(
                content,
                transcript,
                self._text_or_empty(latest.get("display_text", "")),
            )
            item["type"] = "schedule"
            item["date"] = (
                self._text_or_empty(capture.get("date", ""))
                or self._text_or_empty(capture.get("due_date", ""))
                or self._date_from_iso(self._text_or_empty(capture.get("due_at", "")))
                or self._date_from_iso(fallback_due_at)
            )
            item["time"] = (
                self._text_or_empty(capture.get("time", ""))
                or self._text_or_empty(capture.get("time_text", ""))
                or self._time_from_iso(self._text_or_empty(capture.get("due_at", "")))
                or self._time_from_iso(fallback_due_at)
            )
        else:
            due_at = (
                self._text_or_empty(capture.get("due_at", ""))
                or self._text_or_empty(capture.get("trigger_at", ""))
            )
            item["type"] = "alarm"
            item["due_at"] = due_at
            item["time"] = (
                self._text_or_empty(capture.get("time", ""))
                or self._text_or_empty(capture.get("time_text", ""))
                or self._time_from_iso(due_at)
            )

        return list_name, item

    @classmethod
    def _extract_openclaw_capture(cls, latest: dict[str, Any]) -> dict[str, Any] | None:
        execution_result = latest.get("execution_result")
        if not isinstance(execution_result, dict):
            return None
        for candidate in cls._openclaw_capture_candidates(execution_result):
            capture = cls._capture_from_candidate(candidate)
            if capture is not None:
                return capture
        return None

    @classmethod
    def _openclaw_capture_candidates(cls, execution_result: dict[str, Any]) -> Iterable[Any]:
        yield execution_result
        openclaw_result = execution_result.get("openclaw_result")
        if isinstance(openclaw_result, dict):
            yield openclaw_result
            yield openclaw_result.get("openclaw_raw")
            decision = openclaw_result.get("decision")
            if isinstance(decision, dict):
                yield decision
                yield decision.get("raw")
        yield execution_result.get("openclaw_raw")
        raw = execution_result.get("raw")
        if isinstance(raw, dict):
            yield raw

    @classmethod
    def _capture_from_candidate(cls, candidate: Any) -> dict[str, Any] | None:
        if not isinstance(candidate, dict):
            return None
        capture = candidate.get("capture")
        if isinstance(capture, dict):
            return capture
        raw = candidate.get("raw")
        if isinstance(raw, dict) and isinstance(raw.get("capture"), dict):
            return raw["capture"]
        return None

    @classmethod
    def _dashboard_capture_transcript(cls, latest: dict[str, Any]) -> str:
        metadata = latest.get("metadata")
        if isinstance(metadata, dict):
            transcript = cls._text_or_empty(metadata.get("transcript", ""))
            if transcript:
                return transcript

        execution_result = latest.get("execution_result")
        if not isinstance(execution_result, dict):
            return ""
        text = cls._text_or_empty(execution_result.get("text", ""))
        if text:
            return text
        event = execution_result.get("event")
        if isinstance(event, dict):
            payload = event.get("payload")
            if isinstance(payload, dict):
                return cls._text_or_empty(payload.get("text", ""))
        return ""

    @staticmethod
    def _upsert_dashboard_item(items: list[Any], item: dict[str, Any]) -> list[dict[str, Any]]:
        item_id = item.get("id")
        cleaned = [
            existing
            for existing in items
            if isinstance(existing, dict) and existing.get("id") != item_id
        ]
        return [item, *cleaned][:20]

    @staticmethod
    def _date_from_iso(value: str) -> str:
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError:
            return ""

    @staticmethod
    def _time_from_iso(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%H:%M")
        except ValueError:
            return ""

    @staticmethod
    def _datetime_from_capture_text(*values: str) -> str:
        for value in values:
            if not value:
                continue
            match = re.search(
                r"(?P<date>\d{4}-\d{1,2}-\d{1,2})[ T]"
                r"(?P<hour>\d{1,2}):(?P<minute>\d{2})",
                value,
            )
            if not match:
                continue
            try:
                parsed = datetime(
                    int(match.group("date").split("-")[0]),
                    int(match.group("date").split("-")[1]),
                    int(match.group("date").split("-")[2]),
                    int(match.group("hour")),
                    int(match.group("minute")),
                )
            except ValueError:
                continue
            return parsed.isoformat()
        return ""

    def _load_dashboard_snapshot(self) -> dict[str, Any]:
        try:
            raw = self.openclaw_dashboard_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return self._minimal_dashboard_snapshot()
        if not isinstance(data, dict):
            return self._minimal_dashboard_snapshot()
        if data.get("schema") != OPENCLAW_DASHBOARD_SCHEMA:
            return self._minimal_dashboard_snapshot()
        snapshot = self._minimal_dashboard_snapshot()
        snapshot.update(data)
        return snapshot

    @staticmethod
    def _minimal_dashboard_snapshot() -> dict[str, Any]:
        return {
            "schema": OPENCLAW_DASHBOARD_SCHEMA,
            "updated_at": "",
            "mode": "idle",
            "status_text": "",
            "next_item": None,
            "todos": [],
            "schedules": [],
            "reminders": [],
            "latest_reply": {
                "display_text": "",
                "spoken_text": "",
                "source": "",
                "received_at": "",
            },
        }

    @classmethod
    def _dashboard_mode_for_latest(
        cls,
        latest: dict[str, Any],
        dashboard: dict[str, Any],
    ) -> str:
        metadata = latest.get("metadata", {})
        if isinstance(metadata, dict):
            mode = cls._text_or_empty(metadata.get("mode", ""))
            if mode:
                return mode

        for tool_call in latest.get("tool_calls", []):
            if not isinstance(tool_call, dict):
                continue
            name = tool_call.get("name", "")
            canonical_name = ActionExecutor.LEGACY_ROBOT_TOOL_ALIASES.get(
                name,
                name,
            )
            if canonical_name == "xiaoan.robot.care":
                return "care"

        if cls._text_or_empty(latest.get("spoken_text", "")):
            return "speaking"
        return cls._text_or_empty(dashboard.get("mode", "")) or "idle"

    @staticmethod
    def _list_or_empty(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().replace(microsecond=0).isoformat()

    @classmethod
    def _first_say_text(cls, tool_calls: list[dict[str, Any]]) -> str:
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            name = tool_call.get("name", "")
            canonical_name = ActionExecutor.LEGACY_ROBOT_TOOL_ALIASES.get(
                name,
                name,
            )
            if canonical_name != "xiaoan.robot.say":
                continue
            arguments = tool_call.get("arguments", {})
            if not isinstance(arguments, dict):
                continue
            text = cls._text_or_empty(arguments.get("text", ""))
            if text:
                return text
        return ""

    @staticmethod
    def _text_or_empty(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _copy_jsonish(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): ApiRuntime._copy_jsonish(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                ApiRuntime._copy_jsonish(item)
                for item in value
            ]
        return value

    @staticmethod
    def _iter_robot_ack_payloads(result: Any) -> Iterable[dict[str, Any]]:
        if not isinstance(result, dict):
            return

        robot_result = result.get("result")
        if isinstance(robot_result, dict):
            payload = robot_result.get("payload")
            if isinstance(payload, dict):
                yield payload

        for item in result.get("actions", []):
            if not isinstance(item, dict):
                continue
            payload = item.get("payload")
            if isinstance(payload, dict):
                yield payload

    @staticmethod
    def _safe_close(component: Any) -> None:
        close = getattr(component, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                return

    def __enter__(self) -> "ApiRuntime":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
