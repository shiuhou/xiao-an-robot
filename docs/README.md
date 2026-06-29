# Documentation Index

This directory is organized by document purpose. Prefer current entry points over dated snapshots unless you are looking for historical evidence.

## Read Order

1. [current_status.md](current_status.md) - current demo baseline, known working paths, and next checks.
2. [architecture.md](architecture.md) - system architecture overview.
3. [runbooks/main_demo_care_loop.md](runbooks/main_demo_care_loop.md) - reproducible main demo flow.
4. [protocol.md](protocol.md) - WebSocket message contracts.
5. [agents/README.md](agents/README.md) - AI agent handoff, registries, and session protocol.

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
| [runbooks/git_hygiene.md](runbooks/git_hygiene.md) | Git cleanup audit commands and keep/untrack guidance. |
