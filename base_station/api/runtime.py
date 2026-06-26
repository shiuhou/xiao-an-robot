"""Shared object container for the local HTTP API."""

from __future__ import annotations

import asyncio
import os
import threading
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
        verbose: bool = False,
    ):
        self.db_path = str(Path(db_path))
        self.robot_ws_url = robot_ws_url
        self.verbose = bool(verbose)
        self.closed = False
        self._operation_lock = threading.RLock()
        self.robot_connection_status = "unknown_until_command_ack"
        self.robot_connection_detail: dict[str, Any] = {
            "last_checked_by": None,
            "last_tool": None,
            "last_device_id": None,
            "last_forwarded_type": None,
            "last_error": None,
        }

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
            return self.run_async(self.brain.handle_event(event))

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
            "last_error": None,
        }

        for action in executed_actions:
            result = action.get("result", {})
            for payload in self._iter_robot_ack_payloads(result):
                detail["last_device_id"] = payload.get("device_id")
                detail["last_forwarded_type"] = payload.get("forwarded_type")
            self.robot_connection_status = "online_via_command_ack"
            self.robot_connection_detail = detail
            return

        if skipped_actions:
            result = skipped_actions[0].get("result", {})
            error = result.get("error") if isinstance(result, dict) else None
            detail["last_error"] = error or skipped_actions[0].get("reason")
            self.robot_connection_status = "offline_via_command_ack"
            self.robot_connection_detail = detail

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
