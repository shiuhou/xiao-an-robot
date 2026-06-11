# Model Files

This directory is for local model files only. Model binaries are not committed
to Git and should be copied manually to each deployment machine.

## Expected Layout

Place model folders under:

```text
xiao-an-robot/base_station/models/
```

Example:

```text
xiao-an-robot/
└── base_station/
    └── models/
        ├── Qwen2.5-VL-3B-OV-int4/
        │   ├── preprocessor_config.json
        │   ├── tokenizer.json
        │   ├── openvino_model.xml
        │   ├── openvino_model.bin
        │   └── ...
        └── intel/
            ├── face-detection-0206/
            ├── facial-landmarks-35-adas-0002/
            └── head-pose-estimation-adas-0001/
```

The OpenVINO CV backend also expects:

```text
base_station/models/hsemotion/emotion-ferplus-8.onnx
```

## Runtime Paths

For the CV backend, either pass `--model-path` to the model root or set:

```powershell
$env:OPENVINO_MODEL_DIR="D:\path\to\xiao-an-robot\base_station\models"
```

For the VLM backend, pass the Qwen2.5-VL OpenVINO directory:

```powershell
python -m base_station.monitor.emotion_runtime --source opencv_camera --model-backend openvino --enable-vlm-gate --vlm-backend vlm_face --vlm-model-path D:\path\to\Qwen2.5-VL-3B-OV-int4 --fresh-db --verbose
```

## Git Rules

Do not commit model binaries or generated outputs. Keep these local-only:

```text
base_station/models/
manual_outputs/
*.db
*.sqlite
*.onnx
*.xml
*.bin
*.safetensors
*.pt
*.pth
*.gguf
```

Only this README is intentionally tracked.
