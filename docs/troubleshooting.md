# Troubleshooting

Run the environment checker first:

```powershell
python tools/check_runtime_env.py
python tools/check_runtime_env.py --check-camera
```

## `cv2` Missing

Symptom:

- `cv2` is reported as `missing`.
- `--check-camera` reports `reason="cv2_missing"`.

Fix:

- Install OpenCV in the active Python environment when camera testing is needed.
- Re-run `python tools/check_runtime_env.py --check-camera`.

## `openvino` Missing

Symptom:

- `openvino` is reported as `missing`.
- OpenVINO Qwen VL placeholder paths cannot move to real inference yet.

Current status:

- Missing OpenVINO is a warning while fake/mock backends are used.
- Real DK-2500 VLM deployment will require OpenVINO / Optimum Intel exported
  Qwen2.5-VL artifacts.

## Camera Cannot Open

Symptom:

- `--check-camera` returns `ok=false`.
- Reason may be `camera_open_failed` or `frame_read_failed`.

Checks:

- Confirm the camera index is correct:

```powershell
python tools/check_runtime_env.py --check-camera --camera-index 0
python tools/check_runtime_env.py --check-camera --camera-index 1
```

- Close other apps that may hold the camera.
- Check OS camera privacy permissions.
- Use `tools/probe_camera.py` for a frame-read-only test without GUI:

```powershell
python tools/probe_camera.py --camera-index 0 --count 5 --interval 0.2 --verbose
```

## WebSocket Connection Refused

Symptom:

- Agent gateway or command tools cannot connect to `ws://127.0.0.1:8765/agent`.

Checks:

- Confirm the base station WebSocket server is running.
- Confirm the host and port match the command.
- Confirm the path is `/agent` for Agent commands and `/control` for robot/mock robot.
- If port `8765` is occupied, stop the old process or run the server on another port.

## `agent/data` or Model Directories Missing

Symptom:

- Environment checker reports missing paths such as:
  - `agent/data`
  - `base_station/models`
  - `base_station/models/sensevoice-small`
  - `base_station/models/silero-vad`
  - `base_station/models/qwen2_5_vl_openvino`

Fix:

- Create deployment directories during setup.
- Do not commit `.db`, `.sqlite`, model files, or local private paths.
- `schema.sql` is for new SQLite database initialization; migrations are for
  future incremental upgrades.

## Windows Local Shell

On Windows local development, prefer PowerShell or CMD commands. Do not default
to `bash scripts/*.sh` unless you are intentionally working in a Linux shell or
on the target device.

Examples:

```powershell
python -m unittest discover -s tests -v
python -m base_station.monitor.asr_runtime --pattern tired --verbose
python -m base_station.monitor.emotion_runtime --source fake_camera --pattern tired --count 5 --fresh-db --verbose
```
