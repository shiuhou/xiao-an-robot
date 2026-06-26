"""Method and path routing for the local HTTP API."""

from __future__ import annotations

from typing import Any

from base_station.api.response import ApiResponse, error, success


class ApiRouter:
    def __init__(self, runtime: Any):
        self.runtime = runtime

    def route(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body_json: Any = None,
    ) -> ApiResponse:
        active_method = str(method).upper()
        active_path = str(path)

        if active_method == "OPTIONS":
            return success({"cors": True})

        if active_method == "GET" and active_path == "/api/health":
            return success({
                "status": "ok",
                "service": "xiao-an-local-api",
            })

        if active_method == "GET" and active_path == "/api/status":
            return success(self.runtime.status())

        if active_method == "GET" and active_path == "/api/tools":
            return success(self.runtime.list_tools())

        if active_method == "GET" and active_path == "/api/memory/recent":
            return success(self.runtime.query_recent_memory(
                limit=self._query_limit(query, default=20),
                event_type=self._query_value(query, "event_type"),
            ))

        if active_method == "GET" and active_path == "/api/notes":
            return success(self.runtime.query_notes(
                keyword=self._query_value(query, "q", "query"),
                limit=self._query_limit(query, default=20),
            ))

        if active_method == "GET" and active_path == "/api/work-activities":
            return success(self.runtime.query_work_activities(
                keyword=self._query_value(query, "q", "query"),
                limit=self._query_limit(query, default=20),
            ))

        if active_method == "GET" and active_path == "/api/summaries":
            return success(self.runtime.query_summaries(
                summary_type=self._query_value(query, "summary_type"),
                date=self._query_value(query, "date"),
                keyword=self._query_value(query, "q", "query"),
                limit=self._query_limit(query, default=20),
            ))

        if active_method == "GET" and active_path == "/api/tool-runs":
            return success(self.runtime.query_tool_runs(
                tool_name=self._query_value(query, "tool_name"),
                status=self._query_value(query, "status"),
                limit=self._query_limit(query, default=20),
            ))

        if active_method == "GET" and active_path == "/api/tasks":
            return success(self.runtime.query_tasks(
                status=self._query_value(query, "status"),
                include_done=self._query_bool(
                    query,
                    "include_done",
                    default=False,
                ),
                limit=self._query_limit(query, default=20),
            ))

        if active_method == "GET" and active_path == "/api/reminders/due":
            return success(self.runtime.get_due_reminders(
                now_ms=self._query_int(query, "now_ms"),
                limit=self._query_limit(query, default=20),
            ))

        if active_method == "GET" and active_path == "/api/reminders":
            return success(self.runtime.query_reminders(
                status=self._query_value(query, "status"),
                include_fired=self._query_bool(
                    query,
                    "include_fired",
                    default=False,
                ),
                limit=self._query_limit(query, default=20),
            ))

        if active_method == "GET" and active_path == "/api/project/context":
            return success(self.runtime.query_project_context(
                scope=self._query_value(query, "scope"),
                limit=self._query_limit(query, default=5),
            ))

        if active_method == "POST" and active_path == "/api/chat":
            body_or_error = self._validated_text_body(body_json)
            if isinstance(body_or_error, ApiResponse):
                return body_or_error
            text, active_body = body_or_error
            session_id = active_body.get("session_id", "default")
            if not isinstance(session_id, str) or not session_id:
                session_id = "default"
            metadata = active_body.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            return success(self.runtime.chat(
                text=text,
                session_id=session_id,
                metadata=metadata,
            ))

        if active_method == "POST" and active_path == "/api/context/preview":
            body_or_error = self._validated_text_body(body_json)
            if isinstance(body_or_error, ApiResponse):
                return body_or_error
            text, active_body = body_or_error
            session_id = active_body.get("session_id", "default")
            if not isinstance(session_id, str) or not session_id:
                session_id = "default"
            return success(self.runtime.preview_context(
                text=text,
                session_id=session_id,
            ))

        if active_method == "POST" and active_path == "/api/tools/call":
            active_body = body_json if isinstance(body_json, dict) else {}
            tool = active_body.get("tool")
            if not isinstance(tool, str) or not tool.strip():
                return error(
                    code="missing_tool",
                    message="tool must be a non-empty string",
                    status=400,
                )
            arguments = active_body.get("arguments", {})
            if not isinstance(arguments, dict):
                return error(
                    code="invalid_arguments",
                    message="arguments must be an object",
                    status=400,
                )
            session_id = active_body.get("session_id", "default")
            if not isinstance(session_id, str) or not session_id:
                session_id = "default"
            return success(self.runtime.call_tool(
                tool=tool,
                arguments=arguments,
                session_id=session_id,
            ))

        if active_method == "POST" and active_path == "/api/tasks":
            active_body = body_json if isinstance(body_json, dict) else {}
            title = active_body.get("title")
            if not isinstance(title, str) or not title.strip():
                return error(
                    code="missing_title",
                    message="title must be a non-empty string",
                    status=400,
                )
            arguments = {
                key: active_body[key]
                for key in (
                    "title",
                    "description",
                    "priority",
                    "due_at_ms",
                    "due_text",
                    "project_hint",
                )
                if key in active_body
            }
            arguments["title"] = title.strip()
            session_id = self._session_id(active_body)
            result = self.runtime.create_task(
                arguments=arguments,
                session_id=session_id,
            )
            failure = self._tool_failure(result)
            if failure is not None:
                return error(
                    code=failure,
                    message="Task could not be created",
                    status=400,
                    details=result,
                )
            return success(result)

        if active_method == "POST" and active_path == "/api/reminders":
            active_body = body_json if isinstance(body_json, dict) else {}
            message = active_body.get("message")
            if not isinstance(message, str) or not message.strip():
                return error(
                    code="missing_message",
                    message="message must be a non-empty string",
                    status=400,
                )
            delay_seconds = active_body.get("delay_seconds")
            if (
                delay_seconds is not None
                and (
                    isinstance(delay_seconds, bool)
                    or not isinstance(delay_seconds, (int, float))
                )
            ):
                return error(
                    code="invalid_delay_seconds",
                    message="delay_seconds must be a number",
                    status=400,
                )
            arguments = {
                key: active_body[key]
                for key in (
                    "message",
                    "due_at_ms",
                    "delay_seconds",
                    "due_text",
                    "project_hint",
                )
                if key in active_body
            }
            arguments["message"] = message.strip()
            session_id = self._session_id(active_body)
            result = self.runtime.create_reminder(
                arguments=arguments,
                session_id=session_id,
            )
            failure = self._tool_failure(result)
            if failure is not None:
                return error(
                    code=failure,
                    message="Reminder could not be created",
                    status=400,
                    details=result,
                )
            return success(result)

        task_action = self._resource_action(
            active_method,
            active_path,
            resource="tasks",
            actions={"complete", "cancel"},
        )
        if isinstance(task_action, ApiResponse):
            return task_action
        if task_action is not None:
            item_id, action = task_action
            active_body = body_json if isinstance(body_json, dict) else {}
            session_id = self._session_id(active_body)
            result = (
                self.runtime.complete_task(item_id, session_id=session_id)
                if action == "complete"
                else self.runtime.cancel_task(item_id, session_id=session_id)
            )
            failure = self._tool_failure(result)
            if failure is not None:
                return error(
                    code=failure,
                    message=f"Task {item_id} was not found",
                    status=404,
                    details=result,
                )
            return success(result)

        reminder_action = self._resource_action(
            active_method,
            active_path,
            resource="reminders",
            actions={"cancel", "mark-fired"},
        )
        if isinstance(reminder_action, ApiResponse):
            return reminder_action
        if reminder_action is not None:
            item_id, action = reminder_action
            active_body = body_json if isinstance(body_json, dict) else {}
            session_id = self._session_id(active_body)
            if action == "mark-fired":
                fired_at_ms = active_body.get("fired_at_ms")
                if (
                    fired_at_ms is not None
                    and (
                        isinstance(fired_at_ms, bool)
                        or not isinstance(fired_at_ms, int)
                    )
                ):
                    return error(
                        code="invalid_fired_at_ms",
                        message="fired_at_ms must be an integer",
                        status=400,
                    )
                result = self.runtime.mark_reminder_fired(
                    item_id,
                    fired_at_ms=fired_at_ms,
                    session_id=session_id,
                )
                if not result.get("ok", False):
                    return error(
                        code="reminder_not_found",
                        message=f"Reminder {item_id} was not found",
                        status=404,
                        details=result,
                    )
                return success(result)

            result = self.runtime.cancel_reminder(
                item_id,
                session_id=session_id,
            )
            failure = self._tool_failure(result)
            if failure is not None:
                return error(
                    code=failure,
                    message=f"Reminder {item_id} was not found",
                    status=404,
                    details=result,
                )
            return success(result)

        return error(
            code="not_found",
            message=f"No API route for {active_method} {active_path}",
            status=404,
        )

    @staticmethod
    def _validated_text_body(
        body_json: Any,
    ) -> tuple[str, dict[str, Any]] | ApiResponse:
        active_body = body_json if isinstance(body_json, dict) else {}
        text = active_body.get("text")
        if not isinstance(text, str) or not text.strip():
            return error(
                code="missing_text",
                message="text must be a non-empty string",
                status=400,
            )
        return text, active_body

    @staticmethod
    def _session_id(body: dict[str, Any]) -> str:
        session_id = body.get("session_id", "default")
        if not isinstance(session_id, str) or not session_id:
            return "default"
        return session_id

    @staticmethod
    def _resource_action(
        method: str,
        path: str,
        resource: str,
        actions: set[str],
    ) -> tuple[int, str] | ApiResponse | None:
        if method != "POST":
            return None
        parts = path.strip("/").split("/")
        if len(parts) != 4 or parts[0:2] != ["api", resource]:
            return None
        action = parts[3]
        if action not in actions:
            return None
        try:
            item_id = int(parts[2])
        except (TypeError, ValueError):
            return error(
                code="invalid_id",
                message=f"{resource[:-1]} id must be an integer",
                status=400,
            )
        return item_id, action

    @staticmethod
    def _tool_failure(result: dict[str, Any]) -> str | None:
        executor_result = result.get("result", {})
        skipped = executor_result.get("skipped_actions", [])
        if not skipped:
            return None
        local_result = skipped[0].get("result", {})
        return local_result.get("error") or skipped[0].get("reason")

    @staticmethod
    def _query_value(
        query: dict[str, Any] | None,
        *names: str,
    ) -> str | None:
        active_query = query if isinstance(query, dict) else {}
        for name in names:
            value = active_query.get(name)
            if isinstance(value, list):
                value = value[0] if value else None
            if value is not None:
                text = str(value).strip()
                if text:
                    return text
        return None

    @classmethod
    def _query_limit(
        cls,
        query: dict[str, Any] | None,
        default: int,
    ) -> int:
        value = cls._query_value(query, "limit")
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @classmethod
    def _query_bool(
        cls,
        query: dict[str, Any] | None,
        name: str,
        default: bool = False,
    ) -> bool:
        value = cls._query_value(query, name)
        if value is None:
            return default
        normalized = value.lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        return default

    @classmethod
    def _query_int(
        cls,
        query: dict[str, Any] | None,
        name: str,
    ) -> int | None:
        value = cls._query_value(query, name)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
