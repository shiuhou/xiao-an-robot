# OpenClaw Ownership Boundary

Status: Step 30.1 boundary after OpenClaw takeover.

This repository is the robot body and local edge runtime. It is not the source
of truth for the user's profile, long-term memory, task system, reminder
schedule, or narrative reports.

## OpenClaw xiaoan-runtime Owns

- User profile.
- Long-term memory.
- Scheduled reminders.
- Tasks.
- Morning briefs.
- Daily reports.
- Natural-language replies.
- Tool selection and orchestration.

OpenClaw may call approved Xiao An robot tools, but it should not receive local
development permissions or bypass robot safety checks.

Approved robot body tools are listed in
[openclaw_tool_manifest.md](openclaw_tool_manifest.md).

## xiao-an-robot Owns

- Robot body and firmware.
- Local perception chain.
- Local emotion thresholds and trigger gates.
- Safety policy, cooldowns, action mutexes, and hardware protection logic.
- ESP32 communication.
- Robot action execution.
- Local event logs.

The SQLite database in `agent/data/schema.sql` is a Local Event Store. It keeps
emotion samples, interaction traces, tool runs, legacy compatibility rows, and
local diagnostics. It is not the primary source for user long-term memory.

## Legacy Compatibility

These local capabilities remain only so old tests, local API clients, and
diagnostic flows keep working:

- `notes`
- `summaries`
- `tasks`
- `reminders`
- `work_activity`

They should not be described as mainline product capabilities. New product work
should route those responsibilities to OpenClaw xiaoan-runtime.

## Deprecated

`screen_monitoring` is deprecated and exits the MVP. Do not add new product
goals around screen watching or active-window monitoring. Existing files may
stay in place as inert compatibility placeholders until a later cleanup.
