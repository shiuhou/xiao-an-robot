# Main Demo Care Loop Runbook

This runbook captures the current reproducible demo path. Use it with [current_status.md](../current_status.md) and the latest dated snapshot under [../status/](../status/).

For the latest base-station teammate/OpenClaw handoff, start with
[`base_station_openclaw_handoff.md`](base_station_openclaw_handoff.md).

## Scope

The main demo path is:

```text
DK-2500 base-station microphone or camera
  -> base-station ASR / vision observation
  -> OpenClaw / Agent context and decision
  -> /control command
  -> robot movement/expression/sound
  -> matching ack/completed/log evidence
```

For the nine-day demo sprint, the DK-2500/base-station microphone is the primary
voice input. Robot `/audio` remains available as a fallback and diagnostics path,
but the public demo should not depend on the robot microphone.

## Preconditions

- Current P0 spoken-TTS firmware is `mergetesting_care_demo_face240_spoken_tts_din41`.
- The full product-candidate firmware is `mergetesting_full_face240_spoken_tts`
  after MAX98357A DIN is moved to GPIO47.
- `robot/mergetesting/src/config.local.h` is locally configured for the active WiFi and base-station IP. Do not commit this file.
- DK-2500/base station is reachable from the robot.
- DK-2500/base-station microphone capture is available to the ASR runner, or a clearly labeled base-mic WAV sample is available for the same flow.
- Runtime files such as `runtime/latest.jpg` and `runtime/latest_audio.pcm` are treated as local artifacts, not Git inputs.

## Start Base Station

```powershell
$env:XIAOAN_CONTROL_TTS_STREAM='1'
$env:XIAOAN_TTS_TARGET_PEAK='800'
$env:XIAOAN_TTS_VOICE='Microsoft Hanhan Desktop'
python -m base_station.ws_server.server
```

Expected behavior:

- Robot connects to `/control`.
- Server logs `device.hello` and heartbeat/status messages.
- `/video` updates `runtime/latest.jpg` when camera is enabled.
- `/audio` updates PCM/runtime audio artifacts when the robot microphone fallback is enabled.

## Base Mic Demo Target

The base-station teammate should wire the primary spoken-input flow as:

```text
base-station mic capture
-> WAV/audio_file ASR
-> asr.transcript
-> OpenClaw / XiaoAnBrain context
-> robot action plan
-> /agent or /control command forwarding
-> command.ack and motion.completed evidence
```

Minimum user story:

```text
User says "小安，我有点累"
-> ASR text contains a tired/care cue
-> OpenClaw/Agent chooses a care action
-> robot shows caring/happy face
-> robot moves forward briefly
-> robot turns toward the user
-> robot plays audio.play_local care_01
```

## Flash Robot

```powershell
cd robot\mergetesting
pio run -e mergetesting_care_demo_face240_spoken_tts_din41
pio run -e mergetesting_care_demo_face240_spoken_tts_din41 -t upload --upload-port COM23
```

Notes:

- `COM23` was the validated port during the 2026-07-04 P0 spoken-TTS session; verify the live port before flashing.
- USB upload at `460800` was reliable for full firmware during handoff.
- Do not run broad `pio run` for this workflow.
- Current P0 speaker wiring is MAX98357A BCLK=39, LRC/WS=40, DIN=41, with robot mic disabled. If robot mic is required, use the product-candidate DIN=47 path instead.

## Direct Smoke

Run direct repo commands before testing higher-level OpenClaw decisions:

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion left --bench --speed 0.56 --duration-ms 500 --timeout-ms 700
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

For the spoken TTS preflight, use the dedicated one-command runner:

```powershell
python tools\run_openclaw_preflight_p0.py --device-id xiaoan_robot_01
python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01
python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01 --include-motion
```

Full spoken TTS setup details are in
[`spoken_tts_demo_smoke.md`](spoken_tts_demo_smoke.md).

Expected behavior:

- Each command receives `command.ack`.
- Motion commands produce matching `motion.completed` with the same `action_id`.
- Face expression changes visibly.
- Robot moves safely out of the dock area and turns.
- Local sound `care_01` is audible.

## Demo Contract

Use this behavior as the next autonomous target:

1. Receive a base-station mic ASR transcript, or observe latest camera frame.
2. Set expression to `caring` or `happy`.
3. Move forward with `speed=0.56`, `duration_ms=2000`.
4. Wait for matching `motion.completed`.
5. Turn toward the user with `speed=0.56`, `duration_ms=500`.
6. Wait for matching `motion.completed`.
7. Play streamed `audio.play_tts` for short spoken replies, or `audio.play_local care_01` as the fallback chime.
8. Log the observation that caused the action.

## Stop Conditions

Stop the demo and inspect logs if:

- `agent.ack` appears but robot `command.ack` does not.
- `audio.play_tts` is accepted but `audio.playback_done` does not appear.
- A motion command lacks matching `motion.completed`.
- The robot reconnects during motion.
- `runtime/latest.jpg` or audio artifacts stop updating while channels are expected to be active.
- The base-station mic ASR path fails and no labeled fallback text/audio sample is available.
