# Xiao An Local HTTP API

The local API exposes robot-adjacent local runtime state and compatibility
endpoints to local clients. It uses only Python's standard library HTTP server
and listens on `127.0.0.1` by default.

OpenClaw `xiaoan-runtime` owns the main product responsibilities for user
profile, long-term memory, scheduled reminders, tasks, morning briefs, daily
reports, natural-language replies, and tool selection. This API keeps legacy
notes, summaries, reminders, tasks, and work-activity routes so existing tests
and local clients continue to work.

SQLite behind this API is a Local Event Store, not the primary user long-term
memory source.

## Start The Server

Run from the repository root:

```bash
python -m base_station.api.server --host 127.0.0.1 --port 8787 --db-path agent/data/xiao_an.db --verbose
```

The examples below use:

```text
http://127.0.0.1:8787
```

## Response Format

Successful responses use:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

Failed responses use:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "missing_text",
    "message": "text must be a non-empty string",
    "details": null
  }
}
```

Common error codes:

| Code | Meaning |
| --- | --- |
| `missing_text` | A required chat or context-preview text is missing. |
| `missing_tool` | A tool name is missing. |
| `invalid_arguments` | Tool arguments are not a JSON object. |
| `missing_title` | A task title is missing or empty. |
| `invalid_id` | A task or reminder path ID is not an integer. |
| `missing_message` | A reminder message is missing or empty. |
| `invalid_delay_seconds` | `delay_seconds` is not numeric. |
| `not_found` | The requested API route does not exist. |

Business operations can also return specific errors such as
`task_not_found`, `reminder_not_found`, or `missing_reminder_time`.

## Service And Chat

### `GET /api/health`

Checks whether the HTTP service is running.

```bash
curl http://127.0.0.1:8787/api/health
```

### `GET /api/status`

Returns runtime component status and the ownership boundary exposed by Step
30.1.

```bash
curl http://127.0.0.1:8787/api/status
```

Important fields:

- `storage_role`: `local_event_store`
- `openclaw_owned_features`: user profile, long-term memory, reminders, tasks,
  morning briefs, daily reports, natural-language replies, and tool selection.
- `xiao_an_robot_owned_features`: robot body, perception chain, local emotion
  thresholds, safety policy, ESP32 communication, robot action execution, and
  local event logs.
- `deprecated_local_features`: local compatibility or deprecated surfaces such
  as reminders, tasks, notes, summaries, work activity, and screen monitoring.

### `POST /api/chat`

Routes a frontend message through `XiaoAnBrain`.

```bash
curl -X POST http://127.0.0.1:8787/api/chat \
  -H "Content-Type: application/json" \
  -d '{"text":"What tasks are still pending?","session_id":"manual-test","metadata":{"client":"curl"}}'
```

### `POST /api/context/preview`

Builds the context that would be sent to OpenClaw. This endpoint does not call
OpenClaw, execute tools, contact the robot, or write memory events.

```bash
curl -X POST http://127.0.0.1:8787/api/context/preview \
  -H "Content-Type: application/json" \
  -d '{"text":"What tasks are still pending?","session_id":"manual-test"}'
```

## Tools

### `GET /api/tools`

Lists the OpenClaw-facing Xiao An robot tool manifest. The recommended tools
are physical/runtime capabilities:

- `xiaoan.robot.say`
- `xiaoan.robot.expression`
- `xiaoan.robot.move_out`
- `xiaoan.robot.return_to_dock`
- `xiaoan.robot.care`
- `xiaoan.breathing.start`
- `xiaoan.emotion.snapshot`
- `xiaoan.runtime.status`

The response also includes `legacy_tools` for compatibility. Legacy
`note.*`, `task.*`, `reminder.*`, `summary.*`, and `work_context.*` tools are
not recommended to OpenClaw as Xiao An robot body tools.

```bash
curl http://127.0.0.1:8787/api/tools
```

Detailed manifest: [openclaw_tool_manifest.md](openclaw_tool_manifest.md).

### `POST /api/tools/call`

Executes one local tool through the existing action executor.

```bash
curl -X POST http://127.0.0.1:8787/api/tools/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"xiaoan.runtime.status","arguments":{},"session_id":"manual-test"}'
```

Recommended `xiaoan.*` tool calls preserve `tool_runs` behavior. Legacy tool
calls also preserve their existing compatibility writes and `memory_events`.

## Legacy Event And Memory Queries

All endpoints in this section are read-only. They expose the Local Event Store
for diagnostics and legacy clients; they are not the main product source for
long-term user memory.

### `GET /api/memory/recent`

Query parameters:

- `limit`, default `20`
- `event_type`, optional

```bash
curl "http://127.0.0.1:8787/api/memory/recent?event_type=note.add&limit=10"
```

### `GET /api/notes`

Query parameters:

- `q` or `query`, optional keyword
- `limit`, default `20`

```bash
curl "http://127.0.0.1:8787/api/notes?q=API&limit=10"
```

### `GET /api/work-activities`

Query parameters:

- `q` or `query`, optional keyword
- `limit`, default `20`

```bash
curl "http://127.0.0.1:8787/api/work-activities?q=Step%2028&limit=10"
```

### `GET /api/summaries`

Query parameters:

- `summary_type`, optional
- `date`, optional
- `q` or `query`, optional keyword
- `limit`, default `20`

The response uses `content_preview` instead of returning long summary content
by default.

```bash
curl "http://127.0.0.1:8787/api/summaries?summary_type=daily&limit=10"
```

### `GET /api/tool-runs`

Query parameters:

- `tool_name`, optional
- `status`, optional
- `limit`, default `20`

The stored success field is named `status`, for example `success` or `failed`.

```bash
curl "http://127.0.0.1:8787/api/tool-runs?tool_name=note.add&status=success"
```

### `GET /api/tasks`

Query parameters:

- `status`, optional
- `include_done`, accepts `true`, `false`, `1`, `0`, `yes`, or `no`
- `limit`, default `20`

```bash
curl "http://127.0.0.1:8787/api/tasks?include_done=true&limit=20"
```

### `GET /api/reminders`

Query parameters:

- `status`, optional
- `include_fired`, accepts `true`, `false`, `1`, `0`, `yes`, or `no`
- `limit`, default `20`

```bash
curl "http://127.0.0.1:8787/api/reminders?include_fired=true&limit=20"
```

### `GET /api/project/context`

Query parameters:

- `scope`, optional, such as `notes`, `tasks`, or `reminders`
- `limit`, default `5`

```bash
curl "http://127.0.0.1:8787/api/project/context?scope=notes&limit=5"
```

## Task Operations

Task endpoints are legacy compatibility. New product task behavior belongs in
OpenClaw `xiaoan-runtime`.

### `POST /api/tasks`

Required:

- `title`

Optional:

- `description`
- `priority`, default `normal`
- `due_at_ms`
- `due_text`
- `project_hint`
- `session_id`

```bash
curl -X POST http://127.0.0.1:8787/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Finish local API verification","priority":"high","due_text":"today"}'
```

### `POST /api/tasks/{id}/complete`

```bash
curl -X POST http://127.0.0.1:8787/api/tasks/1/complete \
  -H "Content-Type: application/json" \
  -d '{"session_id":"manual-test"}'
```

### `POST /api/tasks/{id}/cancel`

```bash
curl -X POST http://127.0.0.1:8787/api/tasks/1/cancel \
  -H "Content-Type: application/json" \
  -d '{"session_id":"manual-test"}'
```

Task writes reuse `task.add`, `task.complete`, and `task.cancel`, so the task
row, memory event, and tool run remain part of one flow.

## Reminder Operations

Reminder endpoints are legacy compatibility. New product reminder scheduling
belongs in OpenClaw `xiaoan-runtime`.

### `POST /api/reminders`

Required:

- `message`
- One usable schedule, normally `due_at_ms` or `delay_seconds`

Optional:

- `due_text`
- `project_hint`
- `session_id`

```bash
curl -X POST http://127.0.0.1:8787/api/reminders \
  -H "Content-Type: application/json" \
  -d '{"message":"Take a short break","delay_seconds":600}'
```

### `POST /api/reminders/{id}/cancel`

```bash
curl -X POST http://127.0.0.1:8787/api/reminders/1/cancel \
  -H "Content-Type: application/json" \
  -d '{"session_id":"manual-test"}'
```

### `GET /api/reminders/due`

Returns pending reminders whose due time has arrived.

Query parameters:

- `limit`, default `20`
- `now_ms`, optional timestamp override

```bash
curl "http://127.0.0.1:8787/api/reminders/due?limit=10"
```

### `POST /api/reminders/{id}/mark-fired`

Marks a reminder as fired and records the reminder event and tool run.

```bash
curl -X POST http://127.0.0.1:8787/api/reminders/1/mark-fired \
  -H "Content-Type: application/json" \
  -d '{"session_id":"manual-test"}'
```

## Robot Communication Boundary

The Local API does **not** expose `/api/robot/*` endpoints. In particular, it
does not provide HTTP routes for robot speech, care actions, expressions, or
motion.

The robot and base station continue to communicate through WebSocket and
`RobotGateway`. This keeps normal robot execution on the existing control
channel.

A separate Robot Debug API may be added later if a frontend needs explicit
manual robot testing. It is not part of the OpenClaw ownership boundary.

## Deprecated Local Features

Screen monitoring has exited the MVP. Existing screen watcher/report files are
deprecated placeholders and should not be treated as future product goals.
