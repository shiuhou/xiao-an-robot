# Agent Compatibility Layer

This directory contains the repository-local Agent brain, gateway, skills, and compatibility tools.

OpenClaw `xiaoan-runtime` is the user-facing long-term owner: profile, memory, reminders, tasks, reports, natural-language replies, and tool selection. This directory provides local adapters and testable compatibility paths for robot control and runtime integration.

## Main Areas

| Path | Role |
| --- | --- |
| `core/` | `XiaoAnBrain`, `RobotGateway`, action execution, OpenClaw adapters, local tool compatibility. |
| `skills/` | Robot motion, emotion monitor, companion request, breathing, calendar/habit/report compatibility skills. |
| `data/` | SQLite schema and migrations for local event/compatibility storage. |

## Current Role

Use `agent/` for:

- forwarding expression/motion/audio requests to the base station `/agent` route
- testing local robot skills without requiring full OpenClaw runtime
- compatibility with older local tools
- adapters between repository events and OpenClaw-facing concepts

Do not use `agent/` as the long-term memory/task/reminder source of truth. Those belong to OpenClaw.

## Main Robot Path

```text
OpenClaw / local Agent
-> base_station /agent
-> base_station /control
-> robot/mergetesting
```

The current hardware demo should still be verified with direct repo commands before relying on higher-level Agent routing:

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

## Boundaries

- Robot execution belongs to `robot/mergetesting` and `base_station/ws_server`.
- Local event storage is diagnostic/compatibility data, not long-term user memory.
- Screen/work-activity style features are legacy compatibility unless a current status doc says otherwise.
- Protocol changes must be synchronized with [../docs/protocol/protocol.md](../docs/protocol/protocol.md), [../shared/protocol/](../shared/protocol/), base-station protocol helpers, and firmware protocol headers.

## Related Docs

- [../docs/openclaw/openclaw_ownership_boundary.md](../docs/openclaw/openclaw_ownership_boundary.md)
- [../docs/openclaw/openclaw_tool_manifest.md](../docs/openclaw/openclaw_tool_manifest.md)
- [../docs/agents/04_base_station_agent_registry.md](../docs/agents/04_base_station_agent_registry.md)
- [../docs/agents/11_openclaw_robot_integration.md](../docs/agents/11_openclaw_robot_integration.md)
