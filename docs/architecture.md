# Architecture

Xiao An is split into four main modules so hardware, sensing, reasoning, and UI work can move independently.

## Module Responsibilities

- `robot/`: ESP32-S3 firmware for display, motion, microphone stream, camera stream, and WebSocket client behavior.
- `base_station/`: DK2500 edge service for WebSocket channels, audio/video stream handling, OpenVINO perception, and robot session management.
- `agent/`: OpenClaw-style Agent brain, memory, and skills. It decides what to say or do after receiving context.
- `frontend/`: Electron GUI for desktop interaction and operator-facing views.

## WebSocket Channels

- `/control`: Bidirectional JSON control channel. It carries `device.hello`, `device.heartbeat`, motion commands, expression commands, TTS commands, and error reports.
- `/audio`: Robot-to-base-station audio stream. It is intended for VAD, ASR, and voice emotion sensing.
- `/video`: Robot-to-base-station video stream. It is intended for face emotion, head pose, and related perception.

## OpenVINO Perception

OpenVINO belongs in `base_station/perception` because the DK2500 is the edge compute device. The robot should stream sensor data, while the base station performs heavier model inference and turns raw signals into structured events.

## Agent Core and Skills

- `agent/core`: Long-running reasoning, context building, memory access, and gateway logic.
- `agent/skills`: Focused actions the Agent can call, such as motion, calendar, breathing guide, or daily reports.

## Database Schema

`agent/data/schema.sql` defines the SQLite tables used by the Agent. It is the source for creating `agent/data/xiao_an.db` during local setup or DK2500 deployment.

