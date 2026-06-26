# Architecture

Xiao An is split into local robot runtime modules plus OpenClaw `xiaoan-runtime`
ownership so hardware, sensing, safety, and user-facing reasoning can move
independently.

Current status: the architecture is staged. The `/control` route and local simulation paths are the most mature parts; `/video`, `/audio`, real ASR/VAD/TTS, and full hardware integration are still being brought up.

Canonical ownership boundary: [openclaw_ownership_boundary.md](openclaw_ownership_boundary.md).

## Module Responsibilities

- `robot/`: ESP32-S3 firmware for display, motion, camera/mic/speaker tests, and WebSocket client behavior.
- `base_station/`: DK2500 edge service for WebSocket channels, audio/video stream handling, OpenVINO perception, local emotion thresholds, safety-adjacent runtime gates, and robot session management.
- `agent/`: Local gateway, robot skills, event routing, and legacy compatibility tools. It is not the product owner for user profile, long-term memory, tasks, reminders, briefs, reports, reply generation, or tool selection.
- `frontend/`: Electron runtime debug console for Local API status, OpenClaw chat
  inspection, robot action debugging, emotion timeline, and runtime logs. It is
  not the product surface for local long-term memory, reminders, tasks, work
  activity, or screen reports.

OpenClaw `xiaoan-runtime` owns user profile, long-term memory, scheduled
reminders, tasks, morning briefs, daily reports, natural-language replies, and
tool selection. It may choose approved Xiao An robot tools, while this
repository keeps responsibility for the robot body, perception chain, local
emotion gates, safety policy, ESP32 communication, action execution, and local
event logs.

## WebSocket Channels

- `/control`: Bidirectional JSON control channel. It carries `device.hello`, `device.heartbeat`, motion commands, expression commands, TTS commands, and error reports.
- `/audio`: Robot-to-base-station audio stream. It is intended for VAD, ASR, and voice emotion sensing.
- `/video`: Robot-to-base-station video stream. It is intended for face emotion, head pose, and related perception.

Implementation status:

- `/control` exists and is the first hardware integration target.
- `/video` and `/audio` routes exist on the base station. **Live streaming is implemented in `robot/mergetesting`** split envs (`mergetesting_cam_only`, `mergetesting_mic_only`); see `docs/project_status_2026-06-26.md` and `docs/agents/03_mergetesting_registry.md`.
- `robot/firmware` keeps isolated PlatformIO envs for single-subsystem bring-up; DK-2500 integration firmware is **`robot/mergetesting`**, not `robot/firmware/src/main.cpp`.

## OpenVINO Perception

OpenVINO belongs in `base_station/perception` because the DK2500 is the edge compute device. The robot should stream sensor data, while the base station performs heavier model inference and turns raw signals into structured events.

Mock and fake paths are intentionally kept in the codebase so the Agent and WebSocket control loop can be tested before DK-2500 model deployment is complete.

## Agent Core and Skills

- `agent/core`: Local event routing, context compatibility, Local Event Store access, gateway logic, and robot action execution.
- `agent/skills`: Focused local actions the runtime can call, especially robot motion/expression/TTS paths.

Legacy local notes, summaries, reminders, tasks, and work-activity code remains
for API compatibility and test coverage. New user-facing product behavior for
those domains belongs in OpenClaw `xiaoan-runtime`.

Screen monitoring is deprecated and outside the MVP. Do not use
`screen_watcher.py`, `screen_report.py`, or active-window tracking as a future
product target.

## Database Schema

`agent/data/schema.sql` defines the SQLite Local Event Store tables used by the
local robot runtime. It is the source for creating `agent/data/xiao_an.db`
during local setup or DK2500 deployment.

The Local Event Store records emotion samples, interaction traces, tool runs,
legacy compatibility rows, and diagnostics. It is not the source of truth for
user long-term memory; OpenClaw owns that state.

Do not commit generated `.db`, `.sqlite`, logs, or downloaded model files.
