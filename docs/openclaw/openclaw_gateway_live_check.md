# OpenClaw Gateway Live Check

This checklist verifies the real DK-2500 OpenClaw Gateway path for Xiao An.

## Target

- Gateway URL: `ws://127.0.0.1:18789`
- Agent: `xiaoan-runtime`
- Bridge schema: `xiaoan.openclaw.bridge.v1`

## Environment

```bash
export XIAO_AN_OPENCLAW_BACKEND=gateway
export XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789
export XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime
```

`GatewayOpenClawAdapter` uses the OpenClaw Gateway token from
`XIAO_AN_OPENCLAW_GATEWAY_TOKEN` when set. If it is not set, it reads the local
OpenClaw config for loopback development.

## Adapter Probe

Run this from the repository root:

```bash
.venv/bin/python - <<'PY'
import json
from agent.core.gateway_openclaw_adapter import GatewayOpenClawAdapter
from agent.core.openclaw_adapter import OpenClawEvent

adapter = GatewayOpenClawAdapter(
    gateway_url="ws://127.0.0.1:18789",
    agent="xiaoan-runtime",
    timeout_sec=90,
)
event = OpenClawEvent(
    type="frontend.message",
    text="你好小安，请只返回一句简短问候。",
    source="frontend",
    session_id="live-check-probe",
)
response = adapter._run_sync(adapter._send_event(event))
decision = adapter._decision_from_response(response)
print(json.dumps(response, ensure_ascii=False, indent=2))
print("handled:", decision.handled)
print("reply_text:", decision.reply_text)
print("tool_calls:", [tool_call.to_dict() for tool_call in decision.tool_calls])
PY
```

Successful output includes:

```text
handled: True
reply_text: 你好，我在这里。
tool_calls: []
```

## Frontend Smoke

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/send_frontend_message.py "你好小安" --verbose
```

Expected: `handled` is `true` and `reply_text` is non-empty.

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/send_frontend_message.py "让小安出来陪我一下" --verbose
```

Expected: `handled` is `true` and the result includes either a reply or an
`xiaoan.robot.*` tool call such as `xiaoan.robot.care`.

## Mock Robot End-to-End

Terminal 1:

```bash
.venv/bin/python -m base_station.ws_server.server
```

Terminal 2:

```bash
.venv/bin/python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765
```

Terminal 3:

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/send_frontend_message.py "让小安用 caring 表情出来陪我一下" --verbose
```

Successful command output includes:

```json
{
  "handled": true,
  "executed_actions": [
    {"name": "xiaoan.robot.expression"},
    {"name": "xiaoan.robot.move_out"},
    {"name": "xiaoan.robot.say"}
  ]
}
```

Successful `mock_robot` output includes:

```text
< display.expression: {"expression": "caring", ...}
< motion.execute: {"action": "move_out_of_dock", ...}
< audio.play_tts: {"text_preview": "我出来陪你一下。"}
```

## Common Failures

- Gateway not running: connection refused on `127.0.0.1:18789`.
- Missing or wrong Gateway token: `connect` fails with an auth error.
- Runtime cold start too slow: `codex app-server startup timed out`; retry or set
  `XIAO_AN_OPENCLAW_GATEWAY_TIMEOUT_SEC=90`.
- Runtime returns plain text: update `xiaoan-runtime` instructions so
  `xiaoan.openclaw.bridge.v1` messages return JSON only.
- Base station not running: tool calls are skipped with connection refused on
  `127.0.0.1:8765`.
- No robot connected: base station accepts `/agent`, but command forwarding
  cannot produce `display.expression`, `motion.execute`, or `audio.play_tts`.

## Step 32 Entry Criteria

Enter Step 32 only when:

- The adapter probe returns `handled=True`.
- `send_frontend_message.py` works with the `gateway` backend.
- The mock robot receives `display.expression`, `motion.execute`, and
  `audio.play_tts` or `audio.play_local`.
- Full unittest discovery passes.
- No runtime security boundary is weakened.
