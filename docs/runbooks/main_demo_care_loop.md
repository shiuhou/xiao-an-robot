# Main Demo Care Loop Runbook

This runbook captures the current reproducible demo path. Use it with [current_status.md](../current_status.md) and the latest dated snapshot under [../status/](../status/).

## Scope

The main demo path is:

```text
robot camera/audio -> base station/OpenClaw perception -> action decision
  -> /control command -> robot movement/expression/sound
  -> matching ack/completed/log evidence
```

## Preconditions

- Robot is flashed with `mergetesting_full_face240`.
- `robot/mergetesting/src/config.local.h` is locally configured for the active WiFi and base-station IP. Do not commit this file.
- DK-2500/base station is reachable from the robot.
- Runtime files such as `runtime/latest.jpg` and `runtime/latest_audio.pcm` are treated as local artifacts, not Git inputs.

## Start Base Station

```powershell
python -m base_station.ws_server.server
```

Expected behavior:

- Robot connects to `/control`.
- Server logs `device.hello` and heartbeat/status messages.
- `/video` updates `runtime/latest.jpg` when camera is enabled.
- `/audio` updates PCM/runtime audio artifacts when microphone is enabled.

## Flash Robot

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240
pio run -e mergetesting_full_face240 -t upload --upload-port COM19
```

Notes:

- `COM19` was the validated port during the 2026-06-27 hardware session; verify the live port before flashing.
- USB upload at `460800` was reliable for full firmware during handoff.
- Do not run broad `pio run` for this workflow.

## Direct Smoke

Run direct repo commands before testing higher-level OpenClaw decisions:

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion left --bench --speed 0.56 --duration-ms 500 --timeout-ms 700
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

Expected behavior:

- Each command receives `command.ack`.
- Motion commands produce matching `motion.completed` with the same `action_id`.
- Face expression changes visibly.
- Robot moves safely out of the dock area and turns.
- Local sound `care_01` is audible.

## Demo Contract

Use this behavior as the next autonomous target:

1. Observe latest camera frame or receive a tired/care trigger.
2. Set expression to `caring` or `happy`.
3. Move forward with `speed=0.56`, `duration_ms=2000`.
4. Wait for matching `motion.completed`.
5. Turn toward the user with `speed=0.56`, `duration_ms=500`.
6. Wait for matching `motion.completed`.
7. Play `audio.play_local care_01`, or real TTS only after the spoken path is verified.
8. Log the observation that caused the action.

## Stop Conditions

Stop the demo and inspect logs if:

- `agent.ack` appears but robot `command.ack` does not.
- A motion command lacks matching `motion.completed`.
- The robot reconnects during motion.
- `runtime/latest.jpg` or audio artifacts stop updating while channels are expected to be active.
