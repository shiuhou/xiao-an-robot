# Qwen VLM Gate OpenClaw Smoke

Step 41 verifies that real Qwen2.5-VL OpenVINO int4 inference runs inside the `emotion_runtime` VLM gate path, then drives the OpenClaw proactive care loop with a mock robot. It does not use a real camera, ESP32, firmware flashing, ASR, VAD, TTS hardware, or screen monitoring.

## Prerequisites

- `base_station/requirements-vlm.txt` installed into `.venv`.
- `.venv/bin/python tools/setup_models.py --only qwen_vl --check` passes.
- `runtime/manual_samples/image.png` exists locally.
- OpenClaw Gateway is running for the full loop.
- `tests/mocks/mock_robot.py` is running for the full loop.

## No-Agent Image VLM Gate

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source image_file \
  --image-path runtime/manual_samples/image.png \
  --model-backend mock \
  --pattern tired \
  --enable-vlm-gate \
  --vlm-backend openvino_qwen_vl \
  --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --force-vlm \
  --count 1 \
  --no-agent \
  --verbose
```

Expected: `[emotion.frame] source=image_file`, `emotion.sample`, `vlm_triggered=true`, `cv_sample`, and nested real Qwen `vlm` fields.

## No-Agent Fake Camera VLM Gate

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source fake_camera \
  --model-backend mock \
  --pattern tired \
  --enable-vlm-gate \
  --vlm-backend openvino_qwen_vl \
  --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --force-vlm \
  --count 1 \
  --no-agent \
  --verbose
```

Expected: fake camera CV sample remains intact, VLM gate calls real `openvino_qwen_vl`, and final sample includes real nested VLM output.

## OpenClaw And Mock Robot Loop

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
  --source image_file \
  --image-path runtime/manual_samples/image.png \
  --model-backend mock \
  --pattern tired \
  --enable-vlm-gate \
  --vlm-backend openvino_qwen_vl \
  --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --force-vlm \
  --count 1 \
  --db-path agent/data/xiao_an.db \
  --verbose
```

## Local Event Store Queries

```bash
curl "http://127.0.0.1:8787/api/memory/recent?event_type=emotion.intervention&limit=10"
curl "http://127.0.0.1:8787/api/tool-runs?limit=10"
curl "http://127.0.0.1:8787/api/status"
```

## Common Issues

- Qwen returns `neutral`: the VLM gate worked, but proactive care may not trigger. Do not lower production thresholds just for a smoke.
- Real inference is slow: first load is expected to take seconds; record load/generate/total timing.
- Tokenizer warning: current DK-2500 smoke shows a regex warning that does not block inference.
- Missing model directory: run `tools/setup_models.py --only qwen_vl` and then `--check`.
- Missing dependencies: install `base_station/requirements-vlm.txt`; `torchvision`, `qwen_vl_utils`, and `openvino` are required.
- JSON parse failed: inspect `raw_output`; Qwen must return JSON or fenced JSON.
- OpenClaw Gateway not running: emotion intervention delivery will fail or time out.
- mock_robot offline: tool runs may fail with no online robot connected.

Do not commit model files, manual images, `runtime/`, databases, logs, `.venv`, `frontend/dist`, or `node_modules`.
