# Mergetesting Boundary Note

`robot/firmware` and `robot/mergetesting` now have separate jobs:

- `robot/firmware`: robot-body firmware, reusable hardware modules, and isolated bring-up envs.
- `robot/mergetesting`: DK-2500/base-station integration firmware for `/control`, `/video`, and `/audio`.

This file used to describe a plan to fold `robot/mergetesting` back into `robot/firmware`. That direction is superseded. New DK-2500 integration burns should not use firmware-side integration envs.

## Current Rule

When `robot/mergetesting` needs a capability:

1. Validate the robot feature in `robot/firmware` with a dedicated env.
2. Copy or sync the minimal proven module into `robot/mergetesting/src`.
3. Keep the integration loop, WebSocket behavior, and base-station demo commands in `robot/mergetesting`.
4. Do not turn `robot/firmware` into the default DK-2500 demo firmware.

## Historical Snapshot

`robot/firmware/src/archive/integrated_main.cpp` and env `esp32-s3-integrated_legacy` are kept only as a historical snapshot from the earlier consolidation attempt. They are not the recommended path for new burns.

## Correct Commands

Robot-body feature checks:

```powershell
cd robot\firmware
pio run -e motor_manual
pio run -e motor_cam_wifi_manual
pio run -e face240_9expr_merged
pio run -e voice_recognition_test
pio run -e speaker_amp_test
```

DK-2500/base-station integration:

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_face240_only
pio run -e mergetesting_cam_only
pio run -e mergetesting_mic_only
```

See also: `robot/mergetesting/EXTRACTION_MAP.md`, `robot/mergetesting/CAPABILITIES.md`, and `docs/agents/03_mergetesting_registry.md`.
