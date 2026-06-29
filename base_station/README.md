# Base Station

This directory contains the DK-2500-side runtime: WebSocket transport, perception, audio diagnostics, local event storage, and debug APIs.

The base station is the local bridge between the ESP32-S3 robot and OpenClaw/Agent logic. It should keep raw camera/audio local, turn runtime signals into structured events, and forward safe robot commands through WebSocket.

## Main Surfaces

| Path | Role |
| --- | --- |
| `ws_server/` | Main robot transport: `/control`, `/video`, `/audio`, `/agent`. |
| `perception/` | Camera/audio sources, OpenFace/OpenVINO/Qwen paths, ASR/VAD/TTS interfaces, audio diagnostics. `openface_ov_runtime/` is bundled vendored runtime; do not move it during ordinary cleanup. |
| `monitor/` | Emotion runtime, event loop, context builder, SQLite local event store. |
| `api/` | Local debug API for frontend/runtime inspection; not the main product API. |
| `models/` | Local model placement area; large models should not be committed. |
| `config.example.yaml` | Safe template for runtime config. |

## Main Command

Run from the repository root:

```powershell
python -m base_station.ws_server.server
```

Expected robot behavior:

- `/control` receives `device.hello`, heartbeat, status, command ack, and `motion.completed`.
- `/video` receives robot JPEG frames and updates `runtime/latest.jpg`.
- `/audio` receives robot PCM/audio chunks and writes local runtime artifacts.
- `/agent` accepts local Agent/tool commands and forwards them to the robot.

## Boundaries

`ws_server/` is the main transport boundary. Protocol changes must stay aligned with:

- [../docs/protocol.md](../docs/protocol.md)
- [../shared/protocol/](../shared/protocol/)
- `robot/mergetesting/src/protocol.h`
- `base_station/ws_server/protocol.py`

`perception/` contains model/runtime code. Keep raw camera/audio local unless a user explicitly approves another path. Treat `perception/openface_ov_runtime/` as vendored runtime with fragile import paths.

`monitor/` and SQLite are a Local Event Store, not the user's long-term memory source. OpenClaw owns long-term memory, reminders, tasks, and natural-language interaction.

`api/` is for debugging and integration visibility. Do not treat it as the primary product interface.

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
- [../docs/agents/04_base_station_agent_registry.md](../docs/agents/04_base_station_agent_registry.md)
- [../docs/setup/dk2500_deployment.md](../docs/setup/dk2500_deployment.md)
- [../docs/runbooks/main_demo_care_loop.md](../docs/runbooks/main_demo_care_loop.md)
