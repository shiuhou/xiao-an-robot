# Spoken TTS Demo Smoke Runbook

Use this runbook when the speaker hardware is ready and you want one command
sequence to validate the robot-side capabilities that OpenClaw will call.

## Goal

Prove this bottom loop before reconnecting the full base-station ASR pipeline:

```text
base station /agent command
-> /control
-> robot expression / local sound / spoken TTS / motion
-> command.ack, audio.playback_done, motion.completed in server logs
```

This is not the final autonomous OpenClaw test. It is the robot capability
preflight that makes the final ASR -> OpenClaw -> /control demo low-risk.
For the full action-by-action acceptance checklist before connecting OpenClaw,
use `docs/runbooks/openclaw_preflight_acceptance.md`.

## Firmware Choice

Use one of these envs:

| env | Use when | Speaker pins |
| --- | --- | --- |
| `mergetesting_full_face240_spoken_tts` | Full robot demo with face, camera, robot mic fallback, motor, speaker | BCLK 39, LRC 40, DIN 47 |
| `mergetesting_care_demo_face240_spoken_tts` | Safer care demo without camera/robot mic | BCLK 39, LRC 40, DIN 47 |
| `mergetesting_care_demo_face240_spoken_tts_din41` | Temporary fallback if MAX98357A DIN is still wired to GPIO41 | BCLK 39, LRC 40, DIN 41 |

The embedded phrase is configured with `EMBEDDED_TTS_GAIN=32`. On 2026-07-04,
the temporary DIN41 speaker path was hardware-checked: MAX98357A `SD` tied to
3V3, tone probe was loud, `gain=32` and `gain=64` sounded similar, so `gain=32`
is the stable demo value.

Recommended final path:

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240_spoken_tts
pio run -e mergetesting_full_face240_spoken_tts -t upload --upload-port COMxx
```

Temporary GPIO41 speaker-only/care-demo path:

```powershell
cd robot\mergetesting
pio run -e mergetesting_care_demo_face240_spoken_tts_din41
pio run -e mergetesting_care_demo_face240_spoken_tts_din41 -t upload --upload-port COMxx
```

## Hardware Preconditions

- MAX98357A `VIN` on 5V, `GND` common with ESP32.
- MAX98357A `SD` tied to 3V3 for the no-sound debug path.
- Speaker connected across `SPK+` and `SPK-`, not to GND.
- Robot has enough space before enabling motion.
- `robot/mergetesting/src/config.local.h` points to the active base-station IP.

## Start Base Station

From repo root:

```powershell
python -m base_station.ws_server.server
```

For true streamed spoken TTS, start the server with PCM streaming enabled:

```powershell
$env:XIAOAN_CONTROL_TTS_STREAM='1'
python -m base_station.ws_server.server
```

For the current replaced-speaker DIN41 baseline, keep the synthesized PCM peak
at `500`. This matches the buffered robot playback path that was accepted as
clear in live Chinese TTS tests:

```powershell
$env:XIAOAN_CONTROL_TTS_STREAM='1'
$env:XIAOAN_TTS_TARGET_PEAK='500'
python -m base_station.ws_server.server
```

Expected log before running the demo:

```text
Robot connected: xiaoan_robot_01 ...
Robot status: ...
```

## Dry Run the Command Sequence

This prints the exact `/agent` messages without sending them:

```powershell
python tools\run_spoken_tts_demo.py --dry-run
```

## No-Motion Speaker and Face Smoke

Run this first if the robot is on a table or cables are still attached:

```powershell
python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01
```

Expected physical result:

- face switches through `thinking`, `speaking`, `caring`, `happy`
- local `wake_01`, `care_01`, `success_ding` are audible
- `audio.play_tts` speaks the requested text when streaming is enabled, or says
  the embedded phrase when streaming is disabled

Expected base-station logs:

```text
Command ack: type=display.expression status=ok
Command ack: type=audio.play_local status=ok
Command ack: type=audio.play_tts status=accepted
Audio playback done: status=ok bytes_written=97520 duration_ms=...
```

If the TTS step only plays tones, the robot is not flashed with a
`*_spoken_tts` env.

## Full Bottom-Capability Smoke

Only run this when the robot can safely move:

```powershell
python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01 --include-motion
```

Expected extra logs:

```text
Command ack: type=motion.execute status=ok
Motion completed: agent-... -> completed
```

For lifted-wheel bench tests:

```powershell
python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01 --include-motion --bench-motion
```

## How This Connects to Base Mic and OpenClaw

After this runner passes, the base-station teammate should replace the manual
runner with the real decision source:

```text
base mic ASR transcript
-> context object sent to OpenClaw/Agent
-> OpenClaw returns only allowed robot actions
-> same /agent or /control messages used by this runner
-> same robot ack/completed/playback evidence
```

The allowed actions for the demo remain:

- `display.expression`: `listening`, `thinking`, `caring`, `happy`, `speaking`, `neutral`
- `motion.execute`: `move_out_of_dock`, `move_back_to_dock`, `turn`, `stop`
- `audio.play_local`: `care_01`, `wake_01`, `success_ding`
- `audio.play_tts`: first as embedded phrase, later as streamed PCM

## Streamed Spoken TTS Evidence

On 2026-07-08, with the replaced `4 ohm 3 W, 500-5000 Hz` speaker and the
DIN41 buffered firmware path, streamed PCM TTS was accepted as clear over
`/agent -> /control -> ESP32 I2S`:

```text
text="你好，我是小安。請聽我的中文發音清不清楚。"
bytes_written=367384 duration_ms=5763
```

The accepted baseline uses `XIAOAN_CONTROL_TTS_STREAM=1`,
`XIAOAN_TTS_TARGET_PEAK=500`, default SAPI rate, and full PCM buffering before
I2S playback. The expected server evidence is:

```text
Command ack: type=audio.play_tts status=accepted
Audio playback done: status=ok bytes_written=... duration_ms=...
```

`wake_01` remains a local chime, not speech. Arbitrary spoken sentences must
use `audio.play_tts`.

## Stop Conditions

Stop and inspect logs if:

- `/agent` returns `No online robot connected on /control`
- server logs `command.ack status=error`
- `audio.play_tts` returns accepted but no `audio.playback_done` appears
- a motion command has no matching `motion.completed`
- robot resets, reconnects, or heartbeat stops during playback
