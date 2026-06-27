# Model Placement Guide

This repository currently keeps model execution staged. The code and config know where models should live, but downloaded model files are intentionally ignored by Git.

## Expected Directories

`tools/check_runtime_env.py` checks these paths:

```text
agent/data
base_station/models
base_station/models/sensevoice-small
base_station/models/silero-vad
base_station/models/Qwen2.5-VL-3B-OV-int4
```

Create these directories during DK-2500 setup when needed:

```powershell
New-Item -ItemType Directory -Force agent\data | Out-Null
New-Item -ItemType Directory -Force base_station\models | Out-Null
New-Item -ItemType Directory -Force base_station\models\sensevoice-small | Out-Null
New-Item -ItemType Directory -Force base_station\models\silero-vad | Out-Null
New-Item -ItemType Directory -Force base_station\models\Qwen2.5-VL-3B-OV-int4 | Out-Null
```

Linux target equivalent:

```bash
mkdir -p agent/data
mkdir -p base_station/models/sensevoice-small
mkdir -p base_station/models/silero-vad
mkdir -p base_station/models/Qwen2.5-VL-3B-OV-int4
```

## Config Paths

Current `base_station/config.example.yaml` model keys:

```yaml
models:
  face_emotion: "models/emotions-recognition-retail-0003.xml"
  head_pose: "models/head-pose-estimation-adas-0001.xml"
  asr_model: "models/sherpa-onnx-streaming-zipformer-zh"
  vad_model: "models/silero_vad.onnx"
```

Current runtime checker keys:

- `base_station/models/sensevoice-small`
- `base_station/models/silero-vad`
- `base_station/models/Qwen2.5-VL-3B-OV-int4`

Qwen VLM downloads should use `tools/setup_models.py --only qwen_vl`, which reads `base_station/models/models_manifest.json` and verifies sha256 before the model is considered usable.

## Current Runtime Status

| Model Path | Current Role | Status |
| --- | --- | --- |
| OpenVINO face emotion model | CV emotion backend | Interface and tests exist; real postprocessing still staged. |
| Head pose model | Future posture/fatigue feature | Placeholder path only. |
| SenseVoice / sherpa-onnx ASR | Speech transcript source | Interface exists; real model wiring pending. |
| Silero VAD | Voice activity detection | Interface exists; real model wiring pending. |
| Qwen2.5-VL OpenVINO | Heavier VLM emotion/fatigue check | Real static-image OpenVINO Qwen inference has been verified on DK-2500; VLM gate / OpenClaw proactive care is verified in Step 41. |

## Git Rules

Do not commit downloaded model files. `.gitignore` excludes common model artifacts such as:

- `*.bin`
- `*.xml`
- `*.onnx`
- `*.blob`
- `*.pt`
- `*.ckpt`
- `*.safetensors`

Keep only lightweight README/config files in `base_station/models/`.

## Verification

Run from repo root:

```powershell
python tools\check_runtime_env.py
python tools\check_runtime_env.py --json
```

Missing model directories or optional packages currently produce a warning, not a blocker, while fake/mock backends are used.
