# Real Camera Emotion Smoke

Manual smoke for Step 38: feed a real local OpenCV camera into
`emotion_runtime`, then close the software loop through OpenClaw and
`mock_robot`. This smoke does not connect a real ESP32 robot, flash firmware,
run Qwen2.5-VL, or enable ASR/VAD/TTS.

## Safety Boundary

- Use `tests/mocks/mock_robot.py` only.
- Keep `--model-backend mock`; this step validates real camera input, not model
  accuracy.
- Do not save camera images into the repository.
- Do not start ESP32 `/control` or `/video` hardware sessions.
- Do not install OpenVINO, Qwen, FunASR, Torch, ONNXRuntime, SenseVoice, or
  Silero for this smoke.

## Layer 1: Camera Basics

Detect available OpenCV indices:

```bash
.venv/bin/python tools/probe_camera.py --scan-indices 0,1,2,3 --camera-width 640 --camera-height 480 --count 1 --interval 0
```

Probe the selected index:

```bash
.venv/bin/python tools/probe_camera.py --camera-index 0 --camera-width 640 --camera-height 480 --count 3 --interval 0.2 --verbose
```

Run the camera through `emotion_runtime` without the agent:

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source opencv_camera \
  --camera-index 0 \
  --camera-width 640 \
  --camera-height 480 \
  --model-backend mock \
  --pattern neutral \
  --count 3 \
  --interval 0.2 \
  --no-agent \
  --verbose
```

Pass criteria:

- Output contains `source=opencv_camera`.
- `frame_id` increments.
- `timestamp_ms`, `width`, and `height` are visible.
- Exit code is `0`.
- If the camera cannot open, stderr says `unable to open camera index N`.

## Layer 2: Real Frames Become Emotion Samples

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source opencv_camera \
  --camera-index 0 \
  --camera-width 640 \
  --camera-height 480 \
  --model-backend mock \
  --pattern tired \
  --count 3 \
  --interval 0.2 \
  --fresh-db \
  --no-agent \
  --verbose
```

Pass criteria:

- Output contains `[emotion.sample]`.
- Sample payload contains `frame_source=opencv_camera`, `frame_id`,
  `emotion_tag`, `confidence`, and `fatigue_score`.
- `--pattern tired` produces a tired/fatigue sample.
- `--pattern neutral` does not trend toward an intervention.

## Layer 3: OpenClaw Plus Mock Robot Loop

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
.venv/bin/python -m base_station.api.server \
  --host 127.0.0.1 \
  --port 8787 \
  --db-path agent/data/xiao_an.db \
  --verbose
```

Terminal 4:

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source opencv_camera \
  --camera-index 0 \
  --camera-width 640 \
  --camera-height 480 \
  --model-backend mock \
  --pattern tired \
  --count 3 \
  --interval 0.2 \
  --db-path agent/data/xiao_an.db \
  --verbose
```

Check the local event store:

```bash
curl "http://127.0.0.1:8787/api/memory/recent?event_type=emotion.intervention&limit=10"
curl "http://127.0.0.1:8787/api/tool-runs?limit=10"
```

Pass criteria:

- `emotion_runtime` reads real OpenCV frames.
- Tired samples trigger `emotion.intervention`.
- Intervention payload contains `emotion_tag`, `confidence`,
  `fatigue_score`, `reason`, `timestamp`, `source`, `frame_source`, and
  `frame_id`.
- The event is sent to `xiaoan-runtime`.
- OpenClaw returns `reply_text` or `xiaoan.robot.*` `tool_calls`.
- `mock_robot` receives at least one of `display.expression`,
  `motion.execute`, `audio.play_tts`, or `audio.play_local`.
- Local Event Store contains `emotion.intervention` and `tool_runs`.
- A neutral run does not trigger proactive care; cooldown remains active for
  repeated tired frames.

## Layer 4: Frontend Observability

Start or open the frontend against the API server from Layer 3.

Pass criteria:

- Status shows Local API online, `OpenClaw backend=gateway`, Gateway URL,
  `xiaoan-runtime`, and robot/mock online or latest command ack.
- Emotion Timeline shows camera-related `emotion.sample`,
  `emotion.intervention`, or `companion.request`.
- Runtime Logs shows `xiaoan.robot.care`, `xiaoan.robot.say`, or other
  `tool_runs`.
- Robot Debug can manually trigger `xiaoan.robot.care`, and `mock_robot`
  receives the command.

Build check:

```bash
cd frontend && npm run build
```

## If No Camera Is Available

Do not treat missing or busy hardware as a code failure. Record the environment
reason in the smoke result, for example:

```text
Camera manual smoke not run: tools/probe_camera.py reported
unable to open camera index 0.
```

Still run the automated checks:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
cd frontend && npm run build
git diff --check
```
