# OpenClaw Gateway Bridge MVP

Status: Step 30.3.

Xiao An can use a real OpenClaw Gateway instead of the fake adapter. The bridge
sends local runtime events to OpenClaw `xiaoan-runtime`, receives `reply_text`
and/or `tool_calls`, then lets `ActionExecutor` run local `xiaoan.*` tools.

## Enable Gateway Backend

```bash
export XIAO_AN_OPENCLAW_BACKEND=gateway
export XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789
export XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime
```

Optional timeout:

```bash
export XIAO_AN_OPENCLAW_GATEWAY_TIMEOUT_SEC=5
```

Defaults:

- `XIAO_AN_OPENCLAW_BACKEND=fake`
- `XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789`
- `XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime`

## Event Path

```text
frontend.message / asr.transcript / emotion.intervention / companion.request
-> XiaoAnBrain
-> GatewayOpenClawAdapter
-> OpenClaw Gateway
-> xiaoan-runtime
-> OpenClawDecision(reply_text, tool_calls)
-> ActionExecutor
-> local robot actions
```

## Gateway Request

The bridge sends one JSON object per WebSocket connection:

```json
{
  "schema": "xiaoan.openclaw.bridge.v1",
  "type": "xiaoan.event",
  "agent": "xiaoan-runtime",
  "event": {
    "type": "frontend.message",
    "text": "你好小安",
    "source": "frontend",
    "session_id": "default",
    "context": {}
  },
  "tools": []
}
```

`tools` contains the Step 30.2 `xiaoan.*` tool manifest.

## Gateway Response

The bridge accepts direct or wrapped decisions:

```json
{
  "handled": true,
  "reply_text": "你好，我在。",
  "tool_calls": [
    {
      "name": "xiaoan.robot.expression",
      "arguments": {"expression": "happy"}
    }
  ]
}
```

It also accepts `{"decision": {...}}`, `{"result": {...}}`, and
`{"payload": {"decision": {...}}}` forms.

## Offline Behavior

If OpenClaw Gateway is offline, the adapter returns:

```json
{
  "handled": false,
  "raw": {
    "backend": "gateway",
    "error": "...",
    "gateway_url": "ws://127.0.0.1:18789",
    "agent": "xiaoan-runtime"
  }
}
```

`ActionExecutor` surfaces this as `openclaw_raw` and `openclaw_error` in the
final result instead of crashing.

## Manual Smoke Test

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/send_frontend_message.py "你好小安" --verbose
```

The fake backend remains the default for local tests.
