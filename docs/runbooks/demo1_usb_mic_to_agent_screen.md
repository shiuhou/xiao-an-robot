# Demo 1 USB Mic To Agent Screen

## Goal

Demo 1 proves the first public-demo voice loop:

```text
DK-2500 / base-station USB microphone
-> fixed-window WAV recording
-> existing ASR runtime
-> runtime/demo1_transcript.json
-> runtime/demo1_transcript.txt
-> fixed OpenClaw context
-> real OpenClaw Gateway / xiaoan-runtime decision
-> ActionExecutor
-> /agent -> /control robot command path
-> local Agent screen page and JSON logs
```

This is not the full private assistant. It still excludes `/video`, reminders,
long-term memory, and complex OpenClaw tools. For the robot path, the main
Demo 1 route must use real OpenClaw Gateway before local robot execution; the
old local-rule `/agent` route is legacy diagnostics only.

## Hardware

- Plug the USB microphone into the DK-2500 / base-station.
- Keep the microphone selected as an input-capable device in the OS.
- The robot INMP441 `/audio` path is a fallback/diagnostic path, not the primary
  Demo 1 input.

## List Microphone Devices

From the repo root:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py --list-devices
```

Pick the USB microphone index or a unique name fragment for `--device`.
The PyAudio numeric index can change between runs, so prefer the name fragment:

```text
--device USB
```

## Mic Gain Preflight

Before the public run, record one short sentence and check the input peak:

```bash
arecord -D plughw:1,0 -f S16_LE -c 1 -r 16000 -d 5 runtime/demo1_audio/mic_gain_check.wav
ffmpeg -i runtime/demo1_audio/mic_gain_check.wav -af volumedetect -f null -
```

Use the actual `plughw:X,Y` from `--list-devices`. The target is:

```text
max_volume: about -12 dB to -6 dB
not near 0 dB
no clipping
```

If `ffmpeg` is not installed, the Demo 1 tool still reports a built-in level
summary in `runtime/demo1_transcript.json`:

```text
details.input_level.max_volume_dbfs
details.input_level.gain_status
details.input_level.clipping_percent
```

Start with OS/ALSA mic input volume around `60%` to `75%`, then adjust until
`gain_status=ok` or `max_volume_dbfs` is roughly `-10 dBFS`.

## Run Real ASR Demo

The real ASR path records a fixed-window WAV, converts the ASR input to
`16 kHz / mono / pcm_s16le` when needed, calls the existing
`base_station.monitor.asr_runtime` audio-file path, writes
`runtime/demo1_transcript.txt` and `runtime/demo1_transcript.json`, appends
`runtime/demo1_transcript.log.jsonl`, and keeps a local screen page open.

Demo 1 starts with these speech trimming/VAD timing defaults:

```text
vad_backend = energy
vad_threshold = 0.003
min_speech_ms = 350
pre_roll_ms = 250
end_silence_ms = 800
noise_reduction = off
```

One-command run:

```bash
tools/demo/run_demo1_mic_asr.sh
```

One-command text-file check that exits:

```bash
tools/demo/run_demo1_mic_asr.sh --once --no-screen
```

One-command automatic route check:

```bash
tools/demo/run_demo1_mic_to_robot.sh --once --no-screen
```

This writes the ASR text plus:

```text
runtime/demo1_openclaw_context.json
runtime/demo1_action_plan.json
runtime/demo1_openclaw_result.json
```

`runtime/demo1_openclaw_context.json` uses the fixed Demo 1 context schema:

```json
{
  "schema_version": "demo1.openclaw_context.v1",
  "event_type": "asr.transcript",
  "demo_intent": "care_companion",
  "transcript": "小安，我有点累",
  "source": "base_station_mic",
  "transcript_source": "asr",
  "timestamp": "...",
  "robot_state": {"online": "unknown", "busy": "unknown", "battery": "unknown", "dock": "unknown"},
  "vision_context": {"available": false, "summary": ""},
  "last_action": null,
  "allowed_actions": {}
}
```

`runtime/demo1_openclaw_context.json` also includes
`openclaw_tool_contract`. OpenClaw is asked to choose only these Demo 1 tools:

```text
xiaoan.robot.expression
xiaoan.robot.care
xiaoan.robot.move_out
xiaoan.robot.say
```

`runtime/demo1_action_plan.json` is no longer the main decision artifact when
`--route-openclaw` is used. In the main route it records:

```json
{
  "route": "openclaw_gateway",
  "reason": "openclaw_decision_owner",
  "actions": []
}
```

The actual OpenClaw decision and local execution evidence are in:

```text
runtime/demo1_openclaw_result.json
```

The route validates OpenClaw tool calls before executing local robot actions.
Allowed expression values are:

```text
happy, sad, caring, tired, thinking, speaking, idle, surprised, sleeping
```

For Demo 1 the script sends OpenClaw a filtered tool manifest containing only:

```text
xiaoan.robot.expression
xiaoan.robot.care
xiaoan.robot.move_out
xiaoan.robot.say
```

If OpenClaw returns only `reply_text`, an unsupported tool, or an unsupported
expression, the script records a validation failure in
`runtime/demo1_openclaw_result.json` and does not silently fall back to local
rules. On the full route, `openclaw_send.ok=true` requires at least one
validated OpenClaw `tool_call` to execute through `ActionExecutor`.

For the care companion demo, `xiaoan.robot.care` expands locally to caring
expression, short `move_out_of_dock`, and reliable `audio.play_local care_01`.
`xiaoan.robot.say` / `audio.play_tts` is allowed as a text channel, but it is
not the reliable audible proof.

The old `--route-agent` path still exists only for legacy diagnostics. It builds
a local rule action plan and sends that plan through `/agent`; do not treat it
as the main Demo 1 OpenClaw path.

If the OpenClaw Gateway, base-station WebSocket server, or robot is not online,
the failure is recorded in `runtime/demo1_transcript.json` and
`runtime/demo1_openclaw_result.json` instead of being treated as a fake success.

Equivalent expanded command:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --device USB \
  --duration 5 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --route-openclaw \
  --openclaw-gateway-url ws://127.0.0.1:18789 \
  --openclaw-agent xiaoan-runtime
```

Open:

```text
http://localhost:8766
```

For a one-shot CLI check that exits after writing JSON:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --device USB \
  --duration 5 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --route-openclaw \
  --once
```

## Run Mock Fallback

Use this when the microphone, PyAudio, FunASR, or SenseVoice model is not ready.
This does not pretend to be real ASR: the JSON/log source is `mock`.

One-command fallback:

```bash
tools/demo/run_demo1_mic_mock.sh
```

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --mock-text "帮我记一下，今晚八点修改报告第三章"
```

One-shot mock check:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --mock-text "帮我记一下，今晚八点修改报告第三章" \
  --once
```

Mock text can also test the real OpenClaw route without using the microphone:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --mock-text "小安，我有点累" \
  --route-openclaw \
  --once \
  --no-screen
```

Successful output should include:

```text
route_mode: openclaw
openclaw_send.ok: true
decision.tool_calls: xiaoan.robot.care
execution.executed_actions: at least one source=tool_call action
```

When the base-station `/agent` route or robot network is intentionally not part
of the test, use the OpenClaw decision-only test route:

```bash
.venv/bin/python tools/demo/demo1_usb_mic_to_agent_screen.py \
  --mock-text "小安，我有点累" \
  --route-openclaw \
  --openclaw-decision-only \
  --once \
  --no-screen
```

This still calls the real OpenClaw Gateway and validates returned `tool_calls`,
but it does not connect to `ws://127.0.0.1:8765/agent` and it is not robot
execution evidence. Successful decision-only output should include:

```text
route_mode: openclaw
openclaw_send.ok: true
decision.tool_calls: xiaoan.robot.care
execution.mode: openclaw_decision_only
execution.robot_execution_skipped: true
execution.executed_actions: []
```

## Screen Page

The page shows:

- `小安 Demo 1：基站麦克风语音识别`
- status: `idle`, `listening`, `transcribing`, `done`, or `error`
- latest transcript
- timestamp
- audio device name
- error message

API state is also available at:

```text
http://localhost:8766/api/demo1/transcript
```

## Logs And Evidence

The demo writes:

```text
runtime/demo1_transcript.json
runtime/demo1_transcript.txt
runtime/demo1_openclaw_context.json
runtime/demo1_action_plan.json
runtime/demo1_openclaw_result.json
runtime/demo1_transcript.log.jsonl
runtime/demo1_audio/demo1_usb_mic_*.wav
```

`source` must be interpreted honestly:

- `asr`: transcript came from the ASR backend.
- `mock`: transcript came from `--mock-text` or fake ASR fallback.

## Troubleshooting

- No devices listed: verify the USB mic is plugged into DK-2500 and that PyAudio
  is installed in `.venv`.
- Device not selected: pass `--device "USB"` or the current PyAudio USB index
  shown by `--list-devices`.
- `hw:1,0` records silence but the PyAudio USB device works: use
  `--device "USB"`; Demo 1 will convert the ASR input WAV to 16 kHz mono S16
  before transcription.
- ASR backend unavailable: check `funasr` and the local model directory, or run
  the mock fallback command.
- OpenClaw Gateway unavailable: check the `openclaw gateway --port 18789`
  process and retry `--route-openclaw`.
- OpenClaw returns plain text or unsupported tools: update `xiaoan-runtime`
  instructions so `xiaoan.openclaw.bridge.v1` returns JSON with supported
  `xiaoan.robot.*` tool calls.
- `openclaw_send.ok=true` but robot does not move: inspect base-station `/agent`
  and robot `/control` logs; `agent.ack` means forwarded, while robot-side
  `command.ack` / `motion.completed` is the stronger hardware evidence.
- Empty transcript: first check `details.input_level.max_volume_dbfs`; if it is
  below `-25 dBFS`, raise mic input volume. If the sentence tail is cut, retry
  with `--speech-trim-end-padding-ms 1000`. If false triggers happen, raise
  `--speech-trim-threshold`.
- Page does not open: check whether port `8766` is occupied; pass another
  `--port`.
- JSON updates but page is stale: open `/api/demo1/transcript` directly and
  refresh the browser.

## Acceptance Criteria

1. The command can list input-capable audio devices.
2. A selected USB mic can record a fixed-window WAV.
3. The real ASR path calls existing `asr_runtime` and writes an `asr` transcript,
   or the mock fallback writes a clearly labeled `mock` transcript.
4. `runtime/demo1_transcript.json` contains status, transcript, timestamp,
   device, source, and error fields.
5. `runtime/demo1_transcript.txt` contains the latest recognized text.
6. `runtime/demo1_openclaw_context.json` contains the context passed to OpenClaw.
7. `runtime/demo1_openclaw_result.json` contains the OpenClaw Gateway response,
   validated tool calls, and ActionExecutor result.
8. `runtime/demo1_action_plan.json` shows `route=openclaw_gateway` for the main
   path; it must not pretend local rules made the main decision.
9. `http://localhost:8766` clearly displays the latest transcript.
10. `runtime/demo1_transcript.log.jsonl` proves the state chain.
11. With robot online, OpenClaw-triggered actions produce `/agent` ack; final
    hardware acceptance still requires robot-side `command.ack` and, for motion,
    matching `motion.completed`.
