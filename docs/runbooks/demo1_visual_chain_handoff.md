# Demo 1 Visual Chain Handoff

Last updated: 2026-07-03

## Goal

Bring the visual path to the same validation level as the voice Demo 1 path:

```text
real camera frame
-> base_station local visual processing
-> visual / emotion event
-> OpenClaw Gateway / xiaoan-runtime
-> ActionExecutor
-> /agent -> /control
-> robot ack / completed
```

Do not start by tuning model accuracy. First make each small link reproducible.
Use one captured real image as the fixed input before moving back to realtime
video.

## Current Verified State

Stage 3 isolated visual-event-to-OpenClaw smoke passed on port `8875`:

```text
synthetic JPEG frame
-> /video ws_video decoder
-> emotion_runtime
-> fake CV tired sample
-> fake VLM gate
-> real OpenClaw Gateway ws://127.0.0.1:18789
-> xiaoan-runtime
-> ActionExecutor
-> /agent -> /control
-> mock_robot
```

Commands that passed:

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python tools/ops/run_ws_video_runtime.py \
  --host 127.0.0.1 \
  --port 8875 \
  --model-backend mock \
  --pattern tired \
  --vlm-backend fake \
  --force-vlm \
  --fresh-db \
  --verbose
```

```bash
.venv/bin/python tests/mocks/mock_robot.py \
  --host 127.0.0.1 \
  --port 8875 \
  --device-id mock-vision-001
```

```bash
.venv/bin/python tools/probes/send_test_video_frame.py \
  --url ws://127.0.0.1:8875/video \
  --frames 1 \
  --fps 1 \
  --width 320 \
  --height 240
```

Observed output:

- `[emotion.frame] source=ws_video frame_id=1 width=320 height=240`
- `[emotion.sample] ... emotion_tag=tired ... fatigue_score=0.85`
- `vlm_triggered=true`, `fusion.decision=cv_vlm_agree_negative`
- OpenClaw result handled the event and returned `xiaoan.robot.care`
- `mock_robot` received:
  - `audio.play_tts`
  - `display.expression caring`
  - `motion.execute move_out_of_dock`
  - `audio.play_local care_01`

This did not prove real camera quality, OpenFace, Qwen VLM, or real robot
execution. It only proved that a visual event can drive real OpenClaw and the
robot-command path.

## Important Port Note

`tools/ops/run_ws_video_runtime.py` starts its own WebSocket server. Do not run
it on a port that is already occupied by `base_station.ws_server.server`.

Use:

- `8875` for isolated visual smoke with `mock_robot`.
- `8765` only when intentionally replacing the normal base-station server for
  realtime robot `/video` integration.

If `mock_robot` says:

```text
Connection failed: could not reach ws://127.0.0.1:8875/control
```

then `run_ws_video_runtime.py --port 8875` is not running or has crashed.

## Camera-Free Preflight

Before waiting for a fresh robot `runtime/latest.jpg`, run the visual-chain
preflight against any local PNG/JPG. This catches image decode, Python
dependency, OpenFace model, Qwen model, and optional OpenClaw socket issues
without needing the robot camera online:

```bash
.venv/bin/python tools/prepare_visual_chain_preflight.py \
  --image-path runtime/manual_samples/vision_real_camera_0703.jpg
```

When the robot camera is online, use the exact same check with the live frame:

```bash
.venv/bin/python tools/prepare_visual_chain_preflight.py \
  --image-path runtime/latest.jpg
```

The report is written to `runtime/visual_chain_preflight.json` and is not meant
to be committed.

Current expected failure modes are actionable:

- Missing `torchvision` / `openvino`: install the vision requirements into the
  active venv:

```bash
.venv/bin/python -m pip install -r base_station/requirements.txt \
  -r base_station/requirements-vlm.txt
```

- Missing Qwen files: download and verify the OpenVINO Qwen model:

```bash
.venv/bin/python tools/setup_models.py --only qwen_vl
.venv/bin/python tools/setup_models.py --only qwen_vl --check
```

- Missing OpenFace IR files, or files reported as `git-lfs pointer files` under
  `base_station/models/openface_ov`: install Git LFS, run `git lfs pull`, and
  re-run the preflight. If `git lfs version` says `git: 'lfs' is not a git
  command`, install Git LFS on the machine first.

After dependencies and model files are ready, run the heavier real-model checks
before switching to a new camera frame:

```bash
.venv/bin/python tools/prepare_visual_chain_preflight.py \
  --image-path runtime/manual_samples/vision_real_camera_0703.jpg \
  --run-openface
```

```bash
.venv/bin/python tools/prepare_visual_chain_preflight.py \
  --image-path runtime/manual_samples/vision_real_camera_0703.jpg \
  --run-qwen
```

If OpenClaw Gateway should already be up, include:

```bash
.venv/bin/python tools/prepare_visual_chain_preflight.py \
  --image-path runtime/manual_samples/vision_real_camera_0703.jpg \
  --check-openclaw
```

## Next Correct Path

The next work should use one real captured image, then run real local visual
processors against that same image.

### 1. Capture A Real Robot Camera Image

Start the normal base station server and wait for robot `/video`:

```bash
.venv/bin/python -u -m base_station.ws_server.server
```

Expected logs:

```text
New connection on path: /control
New connection on path: /video
Robot connected: xiaoan_robot_01
Robot status: ... camera=cam_ok ...
```

Save the current frame outside Git-tracked paths:

```bash
mkdir -p runtime/manual_samples
cp runtime/latest.jpg runtime/manual_samples/vision_real_camera_0703.jpg
file runtime/manual_samples/vision_real_camera_0703.jpg
```

Pass criteria:

- `runtime/latest.jpg` exists and updates while `/video` is connected.
- The copied image opens locally.
- The image shows the real camera scene expected for the demo.

Do not commit files under `runtime/`.

### 2. Run OpenFace OV On The Fixed Image

Use the real OpenFace/OpenVINO path, not the mock backend:

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source image_file \
  --image-path runtime/manual_samples/vision_real_camera_0703.jpg \
  --model-backend openface_ov \
  --count 1 \
  --no-agent \
  --verbose
```

Default runtime/model locations:

```text
base_station/perception/openface_ov_runtime
base_station/models/openface_ov
```

Pass criteria:

- Output contains `[emotion.frame] source=image_file`.
- Output contains `[emotion.sample]`.
- The sample contains `frame_source=image_file`, `frame_id`, `emotion_tag`,
  `confidence`, `fatigue_score`, and OpenFace-related quality/evidence fields
  when available.
- Missing model/dependency errors are recorded directly; do not replace this
  step with `--model-backend mock`.

### 3. Run Real Qwen VLM On The Fixed Image

Use Qwen as the VLM gate on the same fixed image:

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source image_file \
  --image-path runtime/manual_samples/vision_real_camera_0703.jpg \
  --model-backend openface_ov \
  --enable-vlm-gate \
  --vlm-backend openvino_qwen_vl \
  --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --force-vlm \
  --count 1 \
  --no-agent \
  --verbose
```

Pass criteria:

- `vlm_triggered=true`
- `vlm.executed=true`
- `vlm.status=ok`
- `fusion.strategy=conservative_v1`
- The VLM fields are nested under `vlm`; top-level care policy fields remain
  owned by the CV/OpenFace sample.

If Qwen dependencies or model files are missing, document the exact error and
run:

```bash
.venv/bin/python tools/setup_models.py --only qwen_vl --check
```

### 4. Send The Fixed-Image Visual Event To OpenClaw

After OpenFace and VLM work with `--no-agent`, remove `--no-agent` and connect a
mock robot first:

```bash
.venv/bin/python -m base_station.ws_server.server
```

```bash
.venv/bin/python tests/mocks/mock_robot.py \
  --host 127.0.0.1 \
  --port 8765 \
  --device-id mock-vision-001
```

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source image_file \
  --image-path runtime/manual_samples/vision_real_camera_0703.jpg \
  --model-backend openface_ov \
  --enable-vlm-gate \
  --vlm-backend openvino_qwen_vl \
  --vlm-model-path base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --force-vlm \
  --count 1 \
  --fresh-db \
  --verbose
```

Pass criteria:

- `emotion.sample` is produced from the real image.
- If the sample meets fatigue/negative thresholds, `emotion.intervention` is
  produced.
- OpenClaw receives the event and returns `xiaoan.robot.*` tool calls or a clear
  non-action decision.
- `mock_robot` receives any generated command.

### 5. Move To Real Robot Execution

Only after the fixed-image OpenFace/VLM/OpenClaw loop is stable, replace the
mock robot with the real robot. Expected final path:

```text
fixed real camera image
-> OpenFace OV
-> Qwen VLM gate
-> emotion.intervention
-> OpenClaw
-> /agent -> /control
-> real robot ack / motion.completed
```

## Known Risks

- The fixed image may not contain a face or fatigue cues; that is a data problem
  and should be recorded separately from runtime failure.
- `OpenFace OV models directory not found` means `base_station/models/openface_ov`
  is missing.
- Qwen VLM is expected to be slow on first load.
- Audio in full robot care can still hit `AUDIO_UNSUPPORTED: speaker not ready`
  when TTS and local sound are sent back to back; local sound works in isolation.
