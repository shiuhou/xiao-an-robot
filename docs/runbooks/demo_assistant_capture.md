# Assistant Capture Demo

## Goal

This demo proves the casual voice capture loop:

```text
DK-2500 / base-station microphone
-> fixed-window WAV recording
-> ASR transcript
-> assistant_capture OpenClaw context
-> OpenClaw Gateway / xiaoan-runtime
-> OpenClaw-owned note / idea / reminder / task / meeting capture
-> dashboard and optional robot feedback
```

OpenClaw `xiaoan-runtime` is the source of truth for long-term memory,
reminders, tasks, and calendar-like planning. This repo only owns local ASR
input, robot feedback, dashboard state, WebSocket execution, and local logs.
Do not treat local SQLite `note.*`, `reminder.*`, or `task.*` compatibility
tools as product success evidence.

## Artifacts

The script writes:

```text
runtime/assistant_capture_transcript.txt
runtime/assistant_capture_context.json
runtime/assistant_capture_result.json
runtime/assistant_capture.log.jsonl
```

`assistant_capture_result.json` must include:

```json
{
  "source_of_truth": "openclaw_xiaoan_runtime",
  "local_sqlite_is_product_source": false,
  "capture": {
    "status": "captured",
    "kind": "idea"
  }
}
```

Valid capture statuses are:

```text
captured
needs_clarification
failed
ignored
```

## Mock Context Check

Use this when OpenClaw or the microphone is not ready. It writes the context but
does not claim that anything was saved:

```bash
.venv/bin/python tools/demo/demo_assistant_capture.py \
  --mock-text "这个想法先存一下：做一个主动记事的小安"
```

Expected:

```text
status: ignored
capture.reason: route_openclaw_not_enabled
source_of_truth: openclaw_xiaoan_runtime
```

## OpenClaw Decision-Only Check

Use this when the robot is offline but OpenClaw Gateway is running:

```bash
.venv/bin/python tools/demo/demo_assistant_capture.py \
  --mock-text "帮我记一下，下星期有会议" \
  --route-openclaw \
  --openclaw-decision-only \
  --openclaw-gateway-url ws://127.0.0.1:18789 \
  --openclaw-agent xiaoan-runtime
```

Expected:

```text
status: captured or needs_clarification
capture.source_of_truth: openclaw_xiaoan_runtime
reply_text: OpenClaw confirmation or clarification text
```

For “下星期有会议”, a good result is usually `needs_clarification` with missing
date/time fields.

## Real Mic Check

```bash
.venv/bin/python tools/demo/demo_assistant_capture.py \
  --device USB \
  --duration 5 \
  --asr-backend sensevoice \
  --asr-model-path base_station/models/sensevoice-small \
  --trim-speech \
  --route-openclaw \
  --openclaw-decision-only
```

Say one short target phrase:

```text
帮我记一下，下星期有会议
我突然想到一个点子，帮我记一下
待会提醒我喝水
这个想法先存一下
```

## Robot Feedback Check

Start the base-station WebSocket server and keep the robot connected:

```bash
.venv/bin/python -m base_station.ws_server.server
```

Then run:

```bash
.venv/bin/python tools/demo/demo_assistant_capture.py \
  --mock-text "这个想法先存一下：做一个主动记事的小安" \
  --route-openclaw \
  --feedback-robot
```

Expected local feedback:

```text
captured -> happy expression + success_ding
needs_clarification -> thinking expression
failed -> sad expression
```

Optional spoken confirmation:

```bash
.venv/bin/python tools/demo/demo_assistant_capture.py \
  --mock-text "这个想法先存一下：做一个主动记事的小安" \
  --route-openclaw \
  --feedback-robot \
  --feedback-tts
```

`--feedback-tts` sends `audio.play_tts`, for example “已记录”, but spoken TTS is
not the reliable demo proof yet. Use dashboard state, face expression, and local
sound as the primary confirmation.

## Dashboard

Start:

```bash
.venv/bin/python -m base_station.dashboard.dashboard_server
```

Open:

```text
http://127.0.0.1:8088/dashboard
```

The glance area prioritizes the latest assistant capture result from
`runtime/assistant_capture_result.json`.

## Failure Handling

- ASR no transcript: script exits non-zero and writes `status=error`.
- OpenClaw offline: script exits non-zero and writes `status=failed`; it does
  not save anything locally as a product fallback.
- OpenClaw reply text only: validation fails because `capture` is required.
- Local robot feedback failure: capture may still be successful if OpenClaw
  returned `capture.status=captured`; feedback failure is recorded separately.

## Chain Review Notes

Checked path:

```text
base-station mic/mock text
-> ASR transcript
-> assistant_capture_context.v1
-> OpenClaw Gateway / xiaoan-runtime
-> OpenClaw-owned capture result
-> dashboard / optional robot feedback
```

Current improvements already included:

- The context explicitly marks `source_of_truth=openclaw_xiaoan_runtime`.
- Local SQLite compatibility tools are listed as non-product fallback and are
  rejected if they appear as product capture tool calls.
- OpenClaw `reply_text` alone is not accepted as save success; `capture` is
  required.
- OpenClaw offline writes `failed` and exits non-zero instead of pretending to
  save locally.
- Dashboard reads `runtime/assistant_capture_result.json` and can show captured,
  clarification, and failure states.
- Robot feedback is optional and separate from capture success; local sound and
  face expression are the reliable demo proof, while TTS remains opt-in.

Next practical improvements:

- Align the exact OpenClaw-owned capture result schema with `xiaoan-runtime`
  tool names once that side is finalized.
- Add a real OpenClaw fake-gateway unit test for a full `captured` response if
  future changes make the bridge parsing more complex.
- Add a one-command shell wrapper after the hardware team chooses the exact
  DK-2500 USB mic name on the demo machine.
- Keep tuning ASR target phrases and duration; the current script supports real
  mic, but this session only verified mock/context and offline failure paths.
