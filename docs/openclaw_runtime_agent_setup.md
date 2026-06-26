# OpenClaw Runtime Agent Setup

Status: Step 32 runtime product-brain configuration.

This document records the intended behavior of the OpenClaw `xiaoan-runtime`
agent used by the Xiao An robot bridge.

## Runtime Responsibility

`xiaoan-runtime` is Xiao An's product brain. It owns natural language
understanding, reply generation, user profile interpretation, long-term memory,
reminder/task reasoning, and OpenClaw-native context.

The `xiao-an-robot` repository owns the body side: robot hardware, local
perception, local safety thresholds, action mutexes, cooldowns, local event
logs, and execution of approved robot tools.

Runtime OpenClaw must not receive development permissions. It must not execute
shell, git, arbitrary Python, dependency installs, arbitrary file writes, raw
camera frames, raw microphone audio, raw screenshots, or bypass local robot
safety checks.

## Runtime AGENTS.md Summary

The runtime workspace file
`/home/zzyzsrsyh/.openclaw/workspace-xiaoan-runtime/AGENTS.md` should include
these product rules:

- For `schema=xiaoan.openclaw.bridge.v1`, return only one parseable JSON object.
- Do not add Markdown, code fences, explanations, or debug text outside JSON.
- Treat OpenClaw note/task/reminder/summary/work-context abilities as internal
  reasoning and memory capabilities, not Xiao An body tools.
- Put only approved `xiaoan.*` robot/runtime tools in `tool_calls`.
- Keep replies short and natural.
- Do not repeat `move_out` for `companion.request`, because local pre-response
  already handled caring expression and safe movement.

## JSON Decision Format

Normal reply:

```json
{
  "handled": true,
  "reply_text": "简短自然回复",
  "tool_calls": []
}
```

Robot care action:

```json
{
  "handled": true,
  "reply_text": "我来陪你一下。",
  "tool_calls": [
    {
      "name": "xiaoan.robot.care",
      "arguments": {
        "reason": "user_requested_companion",
        "reply_text": "我来陪你一下。",
        "text": "我来陪你一下。"
      }
    }
  ]
}
```

`reply_text` is the decision-level user-facing response. `arguments.text` is the
short message spoken by the robot for tools that speak. They may be identical.

The gateway adapter accepts wrapped gateway responses, but the runtime agent
itself should make its message content the JSON decision object above.

## Tool Allowlist

Only these Xiao An Bridge tools are allowed in `tool_calls`:

- `xiaoan.robot.say`
- `xiaoan.robot.expression`
- `xiaoan.robot.move_out`
- `xiaoan.robot.return_to_dock`
- `xiaoan.robot.care`
- `xiaoan.breathing.start`
- `xiaoan.emotion.snapshot`
- `xiaoan.runtime.status`

Do not return legacy or OpenClaw-internal tools as robot body calls:

- `note.*`
- `task.*`
- `reminder.*`
- `summary.*`
- `work_context.*`

## Event Strategies

### `frontend.message`

Ordinary messages should only produce `reply_text` with no action tools.

When the user explicitly asks Xiao An to come out, accompany them, comfort them,
move, show an expression, speak, return to dock, or start breathing guidance,
return the relevant allowlisted tool call. For explicit companion or comfort
requests, prefer `xiaoan.robot.care`.

### `asr.transcript`

Ordinary voice requests should receive a short reply and usually no action.

If the user says they are tired, overwhelmed, anxious, breaking down, or asks
for company, `xiaoan.robot.care` is appropriate.

### `companion.request`

The local fast path has already shown a caring expression and moved Xiao An out
of the dock when safe. The runtime should not call `xiaoan.robot.move_out`
again.

Usually return a personalized comfort line and call `xiaoan.robot.say`. Use
`xiaoan.robot.care` only when the local active-care sequence should be completed
or refreshed.

### `emotion.intervention`

Use `emotion_tag`, `confidence`, `fatigue_score`, and `reason` to generate a
brief care response.

High `fatigue_score`, clear anxiety, or obvious distress may trigger
`xiaoan.robot.care`. Low-confidence or mild signals should stay quiet or return
a very light reply. Avoid long lectures, diagnosis, or frequent interruptions.

## Verification

Start or confirm the real OpenClaw Gateway is available on loopback:

```bash
ws://127.0.0.1:18789
```

Run the frontend smoke checks from the repository root:

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/send_frontend_message.py "你好小安" --verbose
```

Expected: `handled=true`, non-empty `reply_text`, and no unnecessary robot
movement or care tool.

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/send_frontend_message.py "让小安出来陪我一下" --verbose
```

Expected: `handled=true` and either `xiaoan.robot.care` or a reasonable
`xiaoan.robot.say` decision. No `note.*`, `task.*`, `reminder.*`, `summary.*`,
or `work_context.*` tool calls should appear.

Run the full test suite without writing bytecode:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
```

