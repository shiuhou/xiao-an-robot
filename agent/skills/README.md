# Agent Skills

These skills are repository-local adapters for robot control and compatibility
tests. They are not the long-term product owner for user memory, schedules,
tasks, reports, or natural-language replies; OpenClaw owns those domains.

## Current Groups

| Group | Files | Role |
| --- | --- | --- |
| Robot demo skills | `robot_motion.py`, `emotion_monitor.py`, `companion_request.py` | Current local bridge for expression/motion/TTS-like commands, emotion-triggered care, and companion requests. |
| Compatibility skills | `breathing_guide.py`, `calendar.py`, `daily_report.py`, `habit_tracker.py`, `morning_brief.py` | Kept for old local skill compatibility and tests. Do not expand these as product owners without an OpenClaw decision. |
| Robot demo skills | `screen_report.py` | Voice-triggered ("汇总屏幕使用…") screen usage report: assembles Markdown from the PC-pushed usage summary cache + today's work_activities, then the brain pushes it to OpenClaw to create a Feishu doc. |

## Rules

- Prefer `robot_motion.py` plus `base_station/ws_server` for current hardware
  command paths.
- Keep calendar/habit/report behavior in OpenClaw-facing flows rather than
  growing local state here.
- When adding a new skill, add tests and document whether it is a current demo
  skill, compatibility shim, or deprecated surface.

## Related Docs

- [../../docs/openclaw/openclaw_ownership_boundary.md](../../docs/openclaw/openclaw_ownership_boundary.md)
- [../../docs/agents/04_base_station_agent_registry.md](../../docs/agents/04_base_station_agent_registry.md)
- [../../docs/current_status.md](../../docs/current_status.md)
