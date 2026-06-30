# Base Station

This directory contains the DK-2500-side runtime: WebSocket transport, perception, audio diagnostics, local event storage, and debug APIs.

The base station is the local bridge between the ESP32-S3 robot and OpenClaw/Agent logic. It should keep raw camera/audio local, turn runtime signals into structured events, and forward safe robot commands through WebSocket.

## Main Surfaces

| Path | Role |
| --- | --- |
| `ws_server/` | Main robot transport: `/control`, `/video`, `/audio`, `/agent`. |
| `perception/` | Camera/audio sources, OpenFace/OpenVINO/Qwen paths, ASR/VAD/TTS interfaces, audio diagnostics. See `perception/README.md` before moving files. |
| `monitor/` | Emotion runtime, event loop, ASR runtime helpers, context builder, SQLite local event store. See `monitor/README.md` for deprecated surfaces. |
| `api/` | Local debug API for frontend/runtime inspection; not the main product API. See `api/README.md`. |
| `dashboard/` | Standalone 7-inch Dock dashboard at `/dashboard` with `/api/dashboard/state`. See `dashboard/README.md`. |
| `models/` | Local model placement area; large models should not be committed. |
| `config.example.yaml` | Safe template for runtime config. |

## Main Command

Run from the repository root:

```powershell
python -m base_station.ws_server.server
```

Run the local Dock dashboard:

```powershell
python -m base_station.dashboard.dashboard_server
```

Open `http://127.0.0.1:8088/dashboard`.

Expected robot behavior:

- `/control` receives `device.hello`, heartbeat, status, command ack, and `motion.completed`.
- `/video` receives robot JPEG frames and updates `runtime/latest.jpg`.
- `/audio` receives robot PCM/audio chunks and writes local runtime artifacts.
- `/agent` accepts local Agent/tool commands and forwards them to the robot.

## Boundaries

`ws_server/` is the main transport boundary. Protocol changes must stay aligned with:

- [../docs/protocol/protocol.md](../docs/protocol/protocol.md)
- [../shared/protocol/](../shared/protocol/)
- `robot/mergetesting/src/protocol.h`
- `base_station/ws_server/protocol.py`

`perception/` contains model/runtime code. Keep raw camera/audio local unless a user explicitly approves another path. Treat `perception/openface_ov_runtime/` as vendored runtime with fragile import paths.

`monitor/` and SQLite are a Local Event Store, not the user's long-term memory source. OpenClaw owns long-term memory, reminders, tasks, and natural-language interaction.

`api/` is for debugging and integration visibility. Do not treat it as the primary product interface.

`dashboard/` is a kiosk display surface. It reads mock data from
`base_station/dashboard/data/` until a real trigger event store exists, and it
keeps the right-side panel capped for a 1024x600 screen.

## Local Files

Do not commit:

- `config.local.yaml`
- real `config.yaml` if it contains local IPs, paths, or secrets
- runtime logs
- SQLite databases
- captured audio/video/images
- downloaded model binaries
- virtual environments

Use `config.example.yaml` as the shareable template.

## Related Docs

- [../docs/current_status.md](../docs/current_status.md)
- [../docs/runbooks/base_station_dashboard.md](../docs/runbooks/base_station_dashboard.md)
- [../docs/agents/04_base_station_agent_registry.md](../docs/agents/04_base_station_agent_registry.md)
- [../docs/setup/dk2500_deployment.md](../docs/setup/dk2500_deployment.md)
- [../docs/runbooks/main_demo_care_loop.md](../docs/runbooks/main_demo_care_loop.md)
