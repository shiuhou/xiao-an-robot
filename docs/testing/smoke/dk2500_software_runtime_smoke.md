# DK-2500 Software Runtime Smoke

This is the no-hardware software loop for the DK-2500 development runtime.
Do not connect a real ESP32, flash firmware, start camera/mic streams, or load
real OpenVINO/Qwen/SenseVoice/Silero models for this smoke.

## Goal

Bring up this local loop:

```text
OpenClaw Gateway + xiaoan-runtime
  -> xiao-an-robot Local API
  -> base_station WebSocket server
  -> mock_robot
  -> frontend debug console
```

The loop is healthy when frontend chat or `tools/send_frontend_message.py`
produces an OpenClaw reply or tool call, robot tool calls reach `mock_robot`,
and the Local Event Store records `tool_runs`.

## Terminal Order

Run every long-lived process in its own terminal so logs stay visible.

### 1. OpenClaw Gateway

Start or verify the OpenClaw Gateway outside this repository. It must expose
`xiaoan-runtime` at:

```text
ws://127.0.0.1:18789
```

Fast local port check:

```bash
ss -ltn | grep ':18789'
```

If the port is not listening, start the OpenClaw Gateway/xiaoan-runtime pair
first. This repository does not manage the Gateway process.

### 2. Base Station WebSocket Server

```bash
.venv/bin/python -m base_station.ws_server.server
```

Expected logs after `mock_robot` starts:

```text
New connection on path: /control
Robot connected: mock-robot-001
```

### 3. Mock Robot

```bash
.venv/bin/python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765
```

Expected output after Robot Debug or OpenClaw tool calls:

```text
Received command: display.expression
Received command: motion.execute
Received command: audio.play_tts
```

`audio.play_local` is also acceptable for care/local-audio checks.

### 4. Local API

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python -m base_station.api.server --host 127.0.0.1 --port 8787 --db-path agent/data/xiao_an.db --verbose
```

Equivalent helper:

```bash
bash scripts/start_local_api.sh
```

Check:

```bash
curl http://127.0.0.1:8787/api/health
curl http://127.0.0.1:8787/api/status
```

Important `/api/status` fields:

- `openclaw_backend`: `gateway`
- `openclaw_gateway_url`: `ws://127.0.0.1:18789`
- `openclaw_agent`: `xiaoan-runtime`
- `robot_connection_status`: `unknown_until_command_ack` before the first robot
  tool call, then `online_via_command_ack` or `offline_via_command_ack`.
- `robot_connection_detail`: latest mock/robot `device_id`, forwarded type, or
  error.
- `storage_role`: `local_event_store`
- `deprecated_local_features`: legacy compatibility only.

### 5. Frontend Debug Console

```bash
cd frontend
npm run dev
```

Use the Status page to inspect:

- OpenClaw backend, Gateway URL, and agent.
- Robot/mock status from the latest command acknowledgement.
- Local Event Store path and component readiness.
- OpenClaw-owned features and deprecated local features.

Use Robot Debug to call:

- `xiaoan.robot.expression`
- `xiaoan.robot.move_out`
- `xiaoan.robot.return_to_dock`
- `xiaoan.robot.care`

With `mock_robot` online, these should return successful API results and print
commands in the mock terminal.

### 6. Gateway Smoke

From the repository root:

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/send_frontend_message.py "你好小安，请用 caring 表情回应我" --verbose
```

Pass criteria:

- Output includes an OpenClaw reply or `tool_calls`.
- `mock_robot` receives at least one of `display.expression`,
  `motion.execute`, `audio.play_tts`, or `audio.play_local`.
- Failures are explicit; no path should pretend success when Gateway or robot
  forwarding is offline.

## Local Event Store Checks

After using Robot Debug or frontend chat:

```bash
curl "http://127.0.0.1:8787/api/tool-runs?limit=10"
curl "http://127.0.0.1:8787/api/memory/recent?event_type=tool.run&limit=10"
```

At least one `tool_runs` row should exist for the called tool, such as
`xiaoan.robot.expression`, `xiaoan.robot.care`, or a legacy compatibility tool.

## Build And Test

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
cd frontend && npm run build
```

`frontend/dist/`, `runtime/`, databases, logs, model files, `.venv/`,
`node_modules/`, and real hardware config/secrets must stay out of commits.
