# Agent Core

This directory contains the repository-local Agent compatibility layer. OpenClaw
`xiaoan-runtime` owns user profile, long-term memory, reminders, tasks, reports,
natural-language replies, and tool selection.

## Current Groups

| Group | Files | Role |
| --- | --- | --- |
| Brain / routing | `brain.py`, `action_executor.py`, `xiaoan_tool_manifest.py` | Local event routing and robot/tool-call execution. |
| Gateway | `gateway.py`, `gateway_openclaw_adapter.py`, `openclaw_adapter.py`, `http_openclaw_adapter.py`, `openclaw_adapter_factory.py` | Bridge between local events, OpenClaw, and robot gateway calls. |
| Context | `context_builder.py`, `context_policy.py`, `project_memory.py`, `daily_summary_builder.py` | Compatibility context and summary builders over local data. |
| Local event store | `memory.py`, `memory_recorder.py`, `local_tools.py`, `reminder_scheduler.py` | SQLite-backed diagnostic/compatibility storage and old local tools. |

## Rules

- Do not add product-owned memory/task/reminder behavior here without an
  OpenClaw boundary decision.
- Robot execution still goes through `base_station/ws_server` and
  `robot/mergetesting`.
- Keep compatibility APIs testable, but mark legacy behavior clearly in docs and
  tests.

## Related Docs

- [../../docs/openclaw/openclaw_ownership_boundary.md](../../docs/openclaw/openclaw_ownership_boundary.md)
- [../../docs/setup/local_api.md](../../docs/setup/local_api.md)
- [../data/README.md](../data/README.md)
