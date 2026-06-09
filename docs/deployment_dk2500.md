# DK-2500 Deployment

This guide tracks the current deployment direction for Xiao An on DK-2500.
The project is still in staged integration: local simulation is runnable now,
while real ASR/VAD/VLM model execution is intentionally represented by
interfaces and placeholders.

## Local Simulation vs DK-2500

Windows local development currently uses deterministic fake sources:

- `fake_camera` for camera frames.
- `fake_qwen_vl` for Qwen VL emotion output.
- `base_station.monitor.asr_runtime` for text-only ASR transcript simulation.
- `mock_robot` and the WebSocket `/agent` route for local command forwarding.

DK-2500 deployment will replace those pieces with real sources:

- `opencv_camera` for camera frames.
- `openvino_qwen_vl` for Qwen2.5-VL-3B after OpenVINO export.
- `SenseVoice-Small` for ASR.
- `Silero-VAD` for voice activity detection.

The Qwen2.5-VL-3B deployment route is Optimum Intel / OpenVINO /
OpenVINO GenAI. Do not plan to run it through direct PyTorch Transformers
in production on DK-2500.

## Environment Check

Run these from the repository root. On Windows local development, prefer
PowerShell or CMD:

```powershell
python tools/check_runtime_env.py
python tools/check_runtime_env.py --check-camera
```

The report includes:

- Python version.
- Optional package imports: `cv2`, `openvino`, `funasr`, `torch`, `onnxruntime`.
- Expected model/data directories.
- Optional camera open/read result.
- `overall_status` as `ok`, `warning`, or `error`.

Missing OpenVINO/FunASR/Torch/ONNX Runtime packages are warnings at this stage
because real model execution is not wired yet.

## Expected Paths

The environment checker looks for:

```text
agent/data
base_station/models
base_station/models/sensevoice-small
base_station/models/silero-vad
base_station/models/qwen2_5_vl_openvino
```

The checker does not create these directories. Create or mount them during
deployment setup, and do not commit downloaded model files.

## Local Commands

ASR transcript simulation:

```powershell
python -m base_station.monitor.asr_runtime --pattern tired --verbose
python -m base_station.monitor.asr_runtime --text "我有点累" --verbose
```

Emotion runtime with fake camera:

```powershell
python -m base_station.monitor.emotion_runtime --source fake_camera --pattern tired --count 5 --interval 1 --fresh-db --verbose
```

Emotion runtime with OpenCV camera and mock model:

```powershell
python -m base_station.monitor.emotion_runtime --source opencv_camera --model-backend mock --pattern neutral --count 5 --interval 1 --fresh-db --verbose
```

Do not default to `bash scripts/*.sh` on Windows local development. Use
PowerShell/CMD commands unless you are specifically working inside a Linux
shell on the target device.
