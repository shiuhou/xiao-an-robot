# Agent Skills

These skills are repository-local adapters for robot control and compatibility
tests. They are not the long-term product owner for user memory, schedules,
tasks, reports, or natural-language replies; OpenClaw owns those domains.

## Current Groups

| Group | Files | Role |
| --- | --- | --- |
| Robot demo skills | `robot_motion.py`, `emotion_monitor.py`, `companion_request.py` | Current local bridge for expression/motion/TTS-like commands, emotion-triggered care, and companion requests. |
| Compatibility skills | `breathing_guide.py`, `calendar.py`, `daily_report.py`, `habit_tracker.py`, `morning_brief.py` | Kept for old local skill compatibility and tests. Do not expand these as product owners without an OpenClaw decision. |
| Deprecated | `screen_report.py` | Screen monitoring has exited the current MVP. Kept only for historical compatibility. |

## Rules

- Prefer `robot_motion.py` plus `base_station/ws_server` for current hardware
  command paths.
- Keep calendar/habit/report behavior in OpenClaw-facing flows rather than
  growing local state here.
- Do not extend `screen_report.py` unless screen monitoring is explicitly
  brought back into scope.
- When adding a new skill, add tests and document whether it is a current demo
  skill, compatibility shim, or deprecated surface.

## Related Docs

- [../../docs/openclaw/openclaw_ownership_boundary.md](../../docs/openclaw/openclaw_ownership_boundary.md)
- [../../docs/agents/04_base_station_agent_registry.md](../../docs/agents/04_base_station_agent_registry.md)
- [../../docs/current_status.md](../../docs/current_status.md)
