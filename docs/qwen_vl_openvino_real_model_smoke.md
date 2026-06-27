# Qwen2.5-VL OpenVINO Real Model Smoke

Step 40 validates that DK-2500 can load a local Qwen2.5-VL OpenVINO model directory and run one static-image emotion inference through `OpenVINOQwenVLEmotionModel`.

Step 39 proved the camera-free static image path, fake Qwen JSON output, and `image_file` emotion runtime path. Step 40 is different: it must use a real local OpenVINO/Optimum Intel export when the model and dependencies are present. It does not connect a camera, ESP32, ASR, VAD, TTS, or screen monitor.

## Model Directory

Default path:

```bash
base_station/models/Qwen2.5-VL-3B-OV-int4
```

External paths are also valid:

```bash
/mnt/models/Qwen2.5-VL-3B-OV-int4
~/models/Qwen2.5-VL-3B-OV-int4
```

The directory must be an OpenVINO / Optimum Intel exported Qwen2.5-VL-3B Instruct model directory with top-level OpenVINO `.xml` and `.bin` files plus tokenizer/processor assets. It must not be the original Hugging Face PyTorch model directory.

Step 40 only validates a model directory that already exists locally. Step 40.1 uses the teammate-maintained `tools/setup_models.py` + `base_station/models/models_manifest.json` path to download and sha256-check the public Qwen OpenVINO int4 model.

Never commit `base_station/models/`, `runtime/`, manual images, `.safetensors`, `.bin`, `.onnx`, `.xml`, `.blob`, `.pt`, or `.pth` files.

## Dependency Probe

Do this before installing anything:

```bash
.venv/bin/python - <<'PY'
mods = ["openvino", "transformers", "optimum.intel.openvino", "qwen_vl_utils", "PIL"]
for m in mods:
    try:
        mod = __import__(m, fromlist=["*"])
        print(f"OK {m}: {getattr(mod, '__version__', 'unknown')}")
    except Exception as e:
        print(f"MISSING {m}: {type(e).__name__}: {e}")
PY
```

Class probe:

```bash
.venv/bin/python - <<'PY'
try:
    from optimum.intel.openvino import OVModelForVisualCausalLM
    print("OK OVModelForVisualCausalLM")
except Exception as e:
    print("MISSING OVModelForVisualCausalLM:", type(e).__name__, e)

try:
    from transformers import AutoProcessor
    print("OK AutoProcessor")
except Exception as e:
    print("MISSING AutoProcessor:", type(e).__name__, e)

try:
    from qwen_vl_utils import process_vision_info
    print("OK process_vision_info")
except Exception as e:
    print("MISSING process_vision_info:", type(e).__name__, e)
PY
```

If installation is explicitly approved, install only into `.venv`:

```bash
.venv/bin/python -m pip install -r base_station/requirements-vlm.txt
```

## Fake Output Smoke

```bash
.venv/bin/python tools/probe_qwen_vl_openvino.py \
  --image-path runtime/manual_samples/image.png \
  --fake-output tired \
  --verbose
```

Expected: `frame.source=image_file`, width/height, `raw_output`, and `emotion_sample.frame_source=image_file`.

## Real Model Probe

```bash
.venv/bin/python tools/probe_qwen_vl_openvino.py \
  --image-path runtime/manual_samples/image.png \
  --model-dir base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --device AUTO \
  --verbose
```

Expected: model load completes, generation completes, raw output is JSON or fenced JSON, and `emotion_sample` includes `emotion_tag`, `confidence`, `fatigue_score`, `visual_reason`, `vlm_observation`, `source=openvino_qwen_vl`, `frame_source=image_file`, `frame_id`, `width`, and `height`.

## Emotion Runtime Smoke

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source image_file \
  --image-path runtime/manual_samples/image.png \
  --model-backend openvino_qwen_vl \
  --model-path base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --count 1 \
  --no-agent \
  --verbose
```

This must not connect OpenClaw, robot hardware, camera, ESP32, ASR, VAD, TTS, or screen monitoring.

## Common Errors

- Missing model directory: copy or export the model locally before running the real probe.
- Missing dependencies: install the Step 40 dependencies into `.venv` only after explicit approval.
- `OVModelForVisualCausalLM` import failed: the current runner class name does not match the installed Optimum Intel package.
- Model directory format mismatch: the path is not an OpenVINO/Optimum Intel export or is empty.
- Model load failed: dependencies imported, but Optimum could not load this export/device combination.
- Generation failed: the model loaded, but processor, vision preprocessing, or `generate()` failed.
- JSON parse failed: Qwen returned text that was not JSON or fenced JSON.

## DK-2500 Result 2026-06-27

- Branch: `integration/openclaw-mergetesting-fusion`
- `runtime/manual_samples/image.png`: present.
- `base_station/models/Qwen2.5-VL-3B-OV-int4`: required real model target path.
- Dependency probe: `openvino`, `transformers`, `optimum.intel.openvino`, `qwen_vl_utils`, and `PIL` missing.
- Class probe: `OVModelForVisualCausalLM`, `AutoProcessor`, and `process_vision_info` missing because packages are not installed.
- Fake-output probe: runnable and should remain the fallback smoke when real dependencies/model are absent.
- Real Qwen OpenVINO inference: blocked by missing dependencies and an empty/non-exported model directory.

Do not record Step 40 as real inference complete until the dependency probe passes and the model directory contains a real OpenVINO/Optimum Intel export.
