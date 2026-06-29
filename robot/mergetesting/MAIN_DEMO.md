# Main DK-2500 Demo Firmware

This is the main robot firmware path for the DK-2500/base-station/OpenClaw demo.

Use it with:

- [../../docs/current_status.md](../../docs/current_status.md)
- [../../docs/runbooks/main_demo_care_loop.md](../../docs/runbooks/main_demo_care_loop.md)
- [../../docs/agents/03_mergetesting_registry.md](../../docs/agents/03_mergetesting_registry.md)

## Current Baseline

| Item | Current value |
| --- | --- |
| Main full-demo env | `mergetesting_full_face240` |
| Reliable audible demo path | `audio.play_local care_01` |
| Practical floor motion speed | `0.56` |
| Full-demo upload note | USB upload was reliable at `460800` during handoff |
| Local config | `src/config.local.h` from `src/config.local.example.h`; do not commit |

`audio.play_tts` is not the reliable spoken demo path yet. Use `audio.play_local care_01` unless a real spoken path has been explicitly verified.

## Flash

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240
pio run -e mergetesting_full_face240 -t upload --upload-port COM19
pio device monitor -b 115200
```

`COM19` was the validated 2026-06-27 hardware-session port. Check the live port before flashing.

## Base Station

From the repo root:

```powershell
python -m base_station.ws_server.server
```

Expected robot/control behavior:

- robot connects to `/control`
- base station logs `device.hello`
- robot sends heartbeat/status
- commands return `command.ack`
- motion returns matching `motion.completed` with the same `action_id`

## Direct Smoke

Run direct repo commands before testing higher-level OpenClaw routing:

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion left --bench --speed 0.56 --duration-ms 500 --timeout-ms 700
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

Expected hardware behavior:

- face expression changes
- robot moves forward safely
- robot turns
- `care_01` is audible
- every motion has matching `motion.completed`

## Split Env Checks

Use split envs when isolating a subsystem:

| Env | Purpose |
| --- | --- |
| `mergetesting_display_only` | ST7735 display + motor + speaker + `/control` |
| `mergetesting_face240_only` | 2.4 inch face path |
| `mergetesting_cam_only` | OV2640 JPEG `/video` |
| `mergetesting_mic_only` | INMP441 PCM `/audio` |
| `mergetesting_speaker_only` | speaker isolation; real PCM spoken TTS still diagnostic |
| `mergetesting_motor_only` | motion isolation |

Prefer targeted `pio run -e <env>` checks over broad builds.

## Stop Conditions

Stop and inspect logs if:

- `agent.ack` appears but robot `command.ack` does not
- motion command lacks matching `motion.completed`
- robot reconnects during motion
- `/video` stops updating `runtime/latest.jpg`
- `/audio` stops updating PCM/runtime artifacts when mic is expected

## Boundary

Do not move this integration loop back into `robot/firmware/src/main.cpp`.

When a robot-body feature is needed, validate it in `robot/firmware`, then copy or sync the minimal proven module into this PlatformIO project.
