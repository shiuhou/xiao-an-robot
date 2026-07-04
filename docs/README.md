# Documentation Index

This directory is organized by document purpose. Prefer current entry points over dated snapshots unless you are looking for historical evidence.

## Read Order

1. [current_status.md](current_status.md) - current demo baseline, known working paths, and next checks.
2. [architecture/system_architecture.md](architecture/system_architecture.md) - system architecture overview.
3. [runbooks/base_station_openclaw_handoff.md](runbooks/base_station_openclaw_handoff.md) - current base-station/OpenClaw handoff, P0 tests, and hardware config.
4. [runbooks/main_demo_care_loop.md](runbooks/main_demo_care_loop.md) - reproducible main demo flow.
5. [protocol/protocol.md](protocol/protocol.md) - WebSocket message contracts.
6. [agents/README.md](agents/README.md) - AI agent handoff, registries, and session protocol.

## Truth Priority

When documents disagree, use this order:

1. Live source and `platformio.ini`
2. Root [AGENTS.md](../AGENTS.md)
3. [current_status.md](current_status.md)
4. Latest dated status in [status/](status/)
5. Agent registries in [agents/](agents/)
6. [archive/](archive/)

## Sections

| Path | Purpose |
| --- | --- |
| [architecture/](architecture/) | System architecture and repository ownership boundaries. |
| [protocol/](protocol/) | WebSocket message contracts and channel-level protocol notes. |
| [status/](status/) | Dated project snapshots and hardware evidence. |
| [setup/](setup/) | DK-2500, device, model, frontend, and OpenClaw setup notes. |
| [openclaw/](openclaw/) | OpenClaw ownership boundary, bridge, live checks, and tool manifest. |
| [testing/](testing/) | Test matrix documents and demo-specific test notes. |
| [testing/smoke/](testing/smoke/) | Smoke-test procedures for ASR/VAD, Qwen-VL, DK-2500 runtime, and camera emotion paths. |
| [perception/](perception/) | OpenFace, Qwen-VL, and perception policy notes. |
| [runbooks/](runbooks/) | Operator procedures and troubleshooting. |
| [agents/](agents/) | Agent session protocol, registries, snapshot, and generated inventory. |
| [archive/](archive/) | Superseded material. Do not treat this as current truth. |

## Current Baseline

The main DK-2500 integration firmware lives in `robot/mergetesting`, not `robot/firmware`. Hardware bring-up and reusable module validation remain in `robot/firmware`.

For the latest full hardware/OpenClaw status, start from [current_status.md](current_status.md), then inspect the most recent file in [status/](status/).

## Robot Firmware Entrypoints

| Path | Purpose |
| --- | --- |
| [../robot/README.md](../robot/README.md) | Top-level robot firmware boundary: mergetesting vs firmware. |
| [../robot/mergetesting/MAIN_DEMO.md](../robot/mergetesting/MAIN_DEMO.md) | Current DK-2500/OpenClaw demo firmware, commands, and stop conditions. |
| [../robot/firmware/README.md](../robot/firmware/README.md) | Robot-body bring-up env groups and legacy/experimental classification. |

## Runtime Entrypoints

| Path | Purpose |
| --- | --- |
| [../base_station/README.md](../base_station/README.md) | DK-2500 runtime boundaries: WebSocket, perception, monitor, debug API. |
| [../agent/README.md](../agent/README.md) | Local Agent compatibility layer and OpenClaw ownership boundary. |
| [../tools/README.md](../tools/README.md) | Operation, probe, setup, maintenance, and legacy tool grouping. |
| [../scripts/README.md](../scripts/README.md) | Setup/start/debug script grouping. |
| [setup/hardware_setup.md](setup/hardware_setup.md) | Hardware wiring bring-up order and target-side checks. |
| [setup/local_api.md](setup/local_api.md) | Local HTTP API routes for the debug console. |
| [runbooks/base_station_openclaw_handoff.md](runbooks/base_station_openclaw_handoff.md) | Current base-station mic/OpenClaw handoff, P0 preflight, TTS env, and speaker pin assumptions. |
| [runbooks/openclaw_preflight_acceptance.md](runbooks/openclaw_preflight_acceptance.md) | P0/P1/P2 acceptance checklist before connecting real OpenClaw. |
| [runbooks/base_station_dashboard.md](runbooks/base_station_dashboard.md) | 7-inch Dock dashboard operation and acceptance notes. |
| [runbooks/integration_console.md](runbooks/integration_console.md) | DK-2500 Integration Console for hardware bring-up, manual robot control, scenarios, tools, and log export. |
| [runbooks/git_hygiene.md](runbooks/git_hygiene.md) | Git cleanup audit commands and keep/untrack guidance. |
| [setup/m600_deployment.md](setup/m600_deployment.md) | Morefine M600 base-station bring-up note. |
