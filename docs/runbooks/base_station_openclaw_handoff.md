# Base Station And OpenClaw Handoff

Last updated: 2026-07-04

Use this document to align the base-station teammate and the OpenClaw runtime
before running the full demo. It records the current working baseline, the
hardware assumptions, and the acceptance tests that must stay true.

## Current Demo Mainline

The demo input is the base-station microphone and/or base-station vision
context, not the robot microphone.

```text
base-station mic or camera
-> ASR transcript / vision context
-> OpenClaw context object
-> OpenClaw chooses one allowed robot action
-> base_station /agent
-> robot /control
-> robot physical action
-> command.ack / audio.playback_done / motion.completed evidence
```

Do not replace OpenClaw decisions with local keyword rules for the final demo.
Local rules are allowed only as explicitly labeled fallback diagnostics.

## What Is Live Now

| Area | Current state |
| --- | --- |
| Branch | `0702base_mic` |
| Base-station server | `python -m base_station.ws_server.server` |
| Robot device id | `xiaoan_robot_01` |
| Current robot IP seen in test | `192.168.137.184` |
| Base station host IP | `192.168.137.1` |
| P0 tested firmware | `mergetesting_care_demo_face240_spoken_tts_din41` |
| Current speaker pins for P0 | MAX98357A BCLK=GPIO39, LRC/WS=GPIO40, DIN=GPIO41 |
| Current speaker power notes | MAX98357A VIN=5V, GND common, SD tied to 3V3, speaker on SPK+ and SPK- |
| ESP stream gain | `MERGETEST_SPEAKER_STREAM_GAIN=32` |
| Base TTS peak | `XIAOAN_TTS_TARGET_PEAK=500` |
| Base TTS backend | default `runtime/tts_probe/edge_tts_to_wav.py` on Linux; override with `XIAOAN_TTS_COMMAND` |
| TTS transport | base station synthesizes mono PCM and streams it over `/control`; current DIN41 firmware buffers the full PCM before I2S playback |
| Robot mic | Not the public demo input. Disabled in the current P0 `*_din41` firmware. Keep robot `/audio` only as fallback/diagnostics. |
| Base mic | Primary public demo voice input. Its ASR output must become OpenClaw context. |

Important pin clarification:

- The P0-tested temporary speaker wiring uses DIN=GPIO41 and disables robot mic.
- The product candidate with robot mic enabled keeps INMP441 SD=GPIO41 and uses
  MAX98357A DIN=GPIO47.
- Do not use GPIO35/36/37 for the current MAX98357A path on the ESP32-S3 Octal
  PSRAM module.

## Start The Working P0 Baseline

Use this exact base-station environment for the current spoken TTS baseline:

```powershell
$env:XIAOAN_TTS_TARGET_PEAK='500'
python -m base_station.ws_server.server
```

Then run:

```powershell
python tools\run_openclaw_preflight_p0.py --device-id xiaoan_robot_01
```

Latest P0 evidence from COM23:

```text
P0-1 Robot online: PASS
P0-2 TTS intro: audio.play_tts accepted; playback_done ok; bytes_written=75750
P0-3 TTS arbitrary sentence: playback_done ok; bytes_written=69872
P0-4 TTS fallback phrase: playback_done ok; bytes_written=71562
P0-5 Local wake_01: command.ack status=ok
P0-6 Face thinking: command.ack status=ok
P0-7 Face speaking: command.ack status=ok
P0-8 Stop motion: command.ack status=ok; detail=stopped
```

The P0 runner does not use local keyword decisions. It sends the same `/agent`
commands that OpenClaw tools should emit, then queries robot-side evidence from
the base-station event cache.

## OpenClaw Context Contract

Every ASR or vision-triggered OpenClaw call should include at least:

```json
{
  "transcript": "user original ASR text",
  "source": "base_station_mic",
  "timestamp": "ISO-8601 or epoch ms",
  "robot_state": {
    "online": true,
    "busy": false,
    "speaking": false,
    "moving": false,
    "battery": 87,
    "docked": false
  },
  "vision_context": {
    "person_present": true,
    "summary": "optional short visual observation"
  },
  "last_action": "last robot command or null",
  "demo_intent": "care_companion"
}
```

For the demo, `source` should be `base_station_mic` for speech. Do not label it
as robot mic unless the robot `/audio` fallback is intentionally being tested.

## OpenClaw Allowed Robot Actions

Restrict OpenClaw to this set before the final demo:

```text
display.expression:
  neutral, thinking, speaking, caring, happy, listening, error

audio.play_tts:
  text: short spoken response, preferably under 30 Chinese characters

audio.play_local:
  wake_01, care_01, success_ding

motion.execute:
  stop, turn, move_out_of_dock, move_back_to_dock
```

OpenClaw must not invent GPIO, PWM, I2S, camera, arbitrary motor, or arbitrary
binary-audio commands. It should emit only tool calls that map to these
`/agent` payloads.

## Required Closed-Loop Evidence

The successful demo is not "OpenClaw returned text". The successful demo is:

```text
ASR or vision trigger
-> context object
-> OpenClaw decision/tool call
-> /agent command
-> robot /control command
-> visible/audible robot action
-> robot-side evidence
```

Evidence to collect:

- `agent.ack ok=true`
- `command.ack status=ok` for expression, local audio, and motion stop
- `command.ack status=accepted` plus `audio.playback_done status=ok` for TTS
- `motion.completed` for any non-stop motion command
- no robot reconnect/reset during speech or motion

## Mic And ASR Boundary

Base-station teammate owns:

- mic capture from the DK-2500/base-station machine
- ASR transcript generation
- transcript/context packaging
- OpenClaw call
- OpenClaw tool result forwarding through `/agent`
- logging transcript -> context -> OpenClaw action -> robot evidence

Robot side owns:

- executing `/control` commands
- reporting `command.ack`, `audio.playback_done`, `motion.completed`, and
  `error.report`
- optional `/video`
- optional robot `/audio` fallback only when explicitly testing that path

## TTS Quality Notes

This Windows base-station PC currently has no zh-CN SAPI voice. The temporary
baseline uses `Microsoft Hanhan Desktop` because it is more Mandarin-compatible
than the zh-HK voices on this machine. The current demo peak is 800; lower
values were too quiet, and higher values risk poorer clarity on the small
speaker.

If time allows, replace the SAPI backend with a higher-quality Mandarin TTS
engine, but keep the same acceptance standard:

```text
audio.play_tts accepted -> audio.playback_done ok -> user can understand the phrase
```

## Stop Conditions

Stop and debug before connecting full OpenClaw autonomy if:

- ASR text is not visibly included in the OpenClaw context.
- OpenClaw uses local keyword rules instead of tool calls.
- OpenClaw emits a command outside the allowed action set.
- `/agent` returns `ok=false`.
- `audio.play_tts` has accepted but no `audio.playback_done`.
- Robot resets, reconnects, or heartbeat stops during speech or motion.
- Motion starts without a matching `motion.completed`.

## Related Files

- `docs/runbooks/openclaw_preflight_acceptance.md`
- `docs/status/2026-07-04-openclaw-p0-preflight.md`
- `docs/runbooks/spoken_tts_demo_smoke.md`
- `tools/run_openclaw_preflight_p0.py`
- `tools/run_spoken_tts_demo.py`
- `base_station/ws_server/server.py`
- `base_station/ws_server/tts_stream.py`
- `robot/mergetesting/platformio.ini`
