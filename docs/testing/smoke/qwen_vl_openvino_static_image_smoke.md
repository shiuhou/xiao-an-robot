# Qwen2.5-VL OpenVINO Static Image Smoke

Step 39 is intentionally camera-free. DK-2500 may not expose `/dev/video*`, so this step validates the Qwen2.5-VL OpenVINO emotion path with a local static image frame instead of continuing camera bring-up.

## Manual Image

Place a local test image at:

```bash
runtime/manual_samples/image.png
```

`runtime/` is ignored by Git. Do not commit manual images, model files, logs, databases, or runtime outputs.

Supported static image inputs are PNG, JPG, and JPEG. The image source emits the same frame metadata shape used by camera sources:

```json
{
  "source": "image_file",
  "frame_id": 1,
  "timestamp_ms": 123,
  "width": 640,
  "height": 480,
  "payload": "<decoded image>"
}
```

## Fake Runner Probe

Use this when the real Qwen/OpenVINO model directory is not deployed yet:

```bash
.venv/bin/python tools/probe_qwen_vl_openvino.py \
  --image-path runtime/manual_samples/image.png \
  --fake-output tired \
  --verbose
```

This decodes the image, feeds it through `OpenVINOQwenVLEmotionModel`, and prints the prompt summary, raw fake JSON, and parsed emotion sample.

## Fake Qwen Runtime Smoke

Use the fake Qwen backend to validate `emotion_runtime` without a real model:

```bash
.venv/bin/python -m base_station.monitor.emotion_runtime \
  --source image_file \
  --image-path runtime/manual_samples/image.png \
  --model-backend qwen_vl \
  --pattern tired \
  --count 1 \
  --no-agent \
  --verbose
```

Expected result: a single `image_file` frame becomes a `fake_qwen_vl` emotion sample with frame metadata preserved.

## Real OpenVINO Qwen Smoke

After a Qwen2.5-VL-3B OpenVINO/Optimum Intel export is prepared locally:

```bash
.venv/bin/python tools/probe_qwen_vl_openvino.py \
  --image-path runtime/manual_samples/image.png \
  --model-dir base_station/models/Qwen2.5-VL-3B-OV-int4 \
  --device AUTO \
  --verbose
```

Runtime equivalent:

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

## Error Meanings

- Missing image path: prepare `runtime/manual_samples/image.png`; do not commit it.
- Decode failure: confirm the file is a valid PNG/JPG/JPEG.
- Missing model directory: download and verify the OpenVINO model into `base_station/models/Qwen2.5-VL-3B-OV-int4` with `tools/setup_models.py --only qwen_vl`.
- Missing dependencies: install the Qwen OpenVINO runtime dependencies in the local environment before real inference.
- No `/dev/video*`: expected for Step 39; static image smoke does not use a camera.

Do not commit model directories, `.safetensors`, `.bin`, `.xml`, manual images, runtime files, databases, logs, `.venv`, `node_modules`, or `frontend/dist`.

The next step is model directory deployment and real Qwen2.5-VL OpenVINO inference/performance validation.
