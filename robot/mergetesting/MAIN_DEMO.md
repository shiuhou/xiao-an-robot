# Main DK-2500 Demo Firmware

This is the main robot firmware path for the DK-2500/base-station/OpenClaw demo.

Use it with:

- [../../docs/current_status.md](../../docs/current_status.md)
- [../../docs/runbooks/base_station_openclaw_handoff.md](../../docs/runbooks/base_station_openclaw_handoff.md)
- [../../docs/runbooks/main_demo_care_loop.md](../../docs/runbooks/main_demo_care_loop.md)
- [../../docs/agents/03_mergetesting_registry.md](../../docs/agents/03_mergetesting_registry.md)

## Current Baseline

| Item | Current value |
| --- | --- |
| Current P0 spoken-TTS env | `mergetesting_care_demo_face240_spoken_tts_din41` |
| Full product-candidate env | `mergetesting_full_face240_spoken_tts` |
| Reliable audible demo path | streamed `audio.play_tts` plus `audio.play_local wake_01/care_01` |
| Current P0 speaker pins | MAX98357A BCLK=39, LRC/WS=40, DIN=41; robot mic disabled |
| Product-candidate speaker pins | MAX98357A BCLK=39, LRC/WS=40, DIN=47; robot mic can keep SD=41 |
| Practical floor motion speed | `0.56` |
| Full-demo upload note | USB upload was reliable at `460800` during handoff |
| Local config | `src/config.local.h` from `src/config.local.example.h`; do not commit |

`audio.play_tts` is now the P0 spoken baseline only when the base station is
started with streamed TTS enabled and the robot is flashed with a `*_spoken_tts`
env. The current tested baseline is documented in
[../../docs/status/2026-07-04-openclaw-p0-preflight.md](../../docs/status/2026-07-04-openclaw-p0-preflight.md).

## Flash

```powershell
cd robot\mergetesting
pio run -e mergetesting_care_demo_face240_spoken_tts_din41
pio run -e mergetesting_care_demo_face240_spoken_tts_din41 -t upload --upload-port COM23
pio device monitor -b 115200
```

`COM23` was the validated 2026-07-04 P0 spoken-TTS port. Check the live port before flashing.

For the full product-candidate wiring after moving MAX98357A DIN to GPIO47:

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240_spoken_tts
pio run -e mergetesting_full_face240_spoken_tts -t upload --upload-port COMxx
```

## Base Station

From the repo root:

```powershell
$env:XIAOAN_CONTROL_TTS_STREAM='1'
$env:XIAOAN_TTS_TARGET_PEAK='500'
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
python tools\run_openclaw_preflight_p0.py --device-id xiaoan_robot_01
```

Expected hardware behavior:

- face expression changes
- robot moves forward safely
- robot turns
- `care_01` or streamed TTS is audible
- every motion has matching `motion.completed`

## Split Env Checks

Use split envs when isolating a subsystem:

| Env | Purpose |
| --- | --- |
| `mergetesting_display_only` | ST7735 display + motor + speaker + `/control` |
| `mergetesting_face240_only` | 2.4 inch face path |
| `mergetesting_cam_only` | OV2640 JPEG `/video` |
| `mergetesting_mic_only` | INMP441 PCM `/audio` |
| `mergetesting_care_demo_face240_spoken_tts_din41` | current P0 spoken-TTS path; speaker DIN=41, robot mic disabled |
| `mergetesting_full_face240_spoken_tts` | full product-candidate spoken-TTS path; speaker DIN=47 |
| `mergetesting_speaker_only` | speaker isolation |
| `mergetesting_motor_only` | motion isolation |

Prefer targeted `pio run -e <env>` checks over broad builds.

## Stop Conditions

Stop and inspect logs if:

- `agent.ack` appears but robot `command.ack` does not
- `audio.play_tts` is accepted but robot `audio.playback_done` does not appear
- motion command lacks matching `motion.completed`
- robot reconnects during motion
- `/video` stops updating `runtime/latest.jpg`
- `/audio` stops updating PCM/runtime artifacts when mic is expected

## Boundary

Do not move this integration loop back into `robot/firmware/src/main.cpp`.

When a robot-body feature is needed, validate it in `robot/firmware`, then copy or sync the minimal proven module into this PlatformIO project.
