# Troubleshooting

Run the environment checker first:

```powershell
python tools\check_runtime_env.py
python tools\check_runtime_env.py --check-camera
```

## Python / Optional Package Warnings

### `cv2` Missing

Symptom:

- `cv2` is reported as `missing`.
- `--check-camera` reports `reason="cv2_missing"`.

Fix:

- Install OpenCV in the active Python environment when camera testing is needed.
- Re-run `python tools/check_runtime_env.py --check-camera`.

### `openvino`, `funasr`, `torch`, or `onnxruntime` Missing

Symptom:

- The environment checker reports optional imports as missing.
- Real OpenVINO/Qwen/ASR paths cannot run.

Current status:

- Missing optional model packages are warnings while fake/mock backends are used.
- Real DK-2500 deployment requires a separate model/runtime setup pass.

## Camera Cannot Open

Symptom:

- `--check-camera` returns `ok=false`.
- Reason may be `camera_open_failed` or `frame_read_failed`.

Checks:

```powershell
python tools/check_runtime_env.py --check-camera --camera-index 0
python tools/check_runtime_env.py --check-camera --camera-index 1
python tools/probe_camera.py --camera-index 0 --count 5 --interval 0.2 --verbose
```

Also check:

- Another app may be holding the camera.
- OS camera privacy permissions may block access.
- The DK-2500 camera index may differ from the local Windows camera index.

## WebSocket Connection Refused

Symptom:

- Agent gateway or command tools cannot connect to `ws://127.0.0.1:8765/agent`.

Checks:

- Confirm the base station WebSocket server is running.
- Confirm host and port match the command.
- Use `/agent` for Agent commands and `/control` for robot/mock robot.
- If port `8765` is occupied, stop the old process or run the server on another port.

## Model or Data Directories Missing

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
- Use [model_download.md](model_download.md) for the current expected placement.

## PlatformIO Env Fails After Dependency Changes

Symptom:

- Build fails with stale `.pio` state, missing dependency metadata, or `.sconsign*.dblite` errors.

Fix:

```powershell
cd robot\firmware
pio run -e motor_cam_wifi_manual -t clean
pio run -e motor_cam_wifi_manual
```

Use the specific env that failed. Avoid broad cleanup unless you intentionally want to rebuild every dependency.

## Wrong PlatformIO Env Uploaded

Symptom:

- Board prints WiFi/AP logs when you expected serial motor logs.
- Board shows motor-only UI when you expected camera stream.
- Firmware seems to ignore the hardware you are testing.

Fix:

Build and upload the dedicated env:

```powershell
cd robot\firmware
pio run -e motor_manual -t upload
pio run -e motor_wifi_manual -t upload
pio run -e motor_cam_wifi_manual -t upload
pio run -e face240_wiretest -t upload
```

## Motor Does Not Move Correctly

Symptom:

- Correct wheel moves but forward/backward is reversed.
- Wrong wheel moves.
- Motor keeps running after release.

Checks:

- Raise the chassis or remove wheels.
- Confirm DRV8833 mapping in [hardware/wiring/motor_driver.md](../hardware/wiring/motor_driver.md).
- Correct wheel, wrong direction: flip `MOTOR_LEFT_FORWARD_USES_IN1` or `MOTOR_RIGHT_FORWARD_USES_IN1`.
- Wrong wheel: change `PIN_MOTOR_*` mapping.
- Continuous motion: disconnect motor power first, then inspect wiring and deadman logs.

## Camera + Motor Demo Has No Stream

Symptom:

- `motor_cam_wifi_manual` control UI loads but video is blank.

Checks:

- Connect to WiFi `XiaoAn-Motor`, password `12345678`.
- Open `http://192.168.4.1/`.
- Open direct stream `http://192.168.4.1:81/stream`.
- Try fallback JPEG `http://192.168.4.1/jpg`.
- Check serial logs for `[MotorCam] camera init failed` or stream capture errors.

## QR Box / Coordinates Are Not Visible

Symptom:

- QR detection works in PC tooling but the live ESP32 stream does not show the QR box.

Fix:

- Use `motor_cam_wifi_manual`, not only `serialqrservo`.
- `serialqrservo` is for PC-side OpenCV QR detection and motor commands.
- `motor_cam_wifi_manual` performs on-device QR decode and draws the overlay before JPEG encoding.

## TFT Display Is Blank or Colors Are Wrong

Symptom:

- Backlight turns on but no image.
- Colors are swapped or inverted.
- 2.4 inch ST7789 module behaves differently from 128x160 ST7735 tests.

Checks:

```powershell
cd robot\firmware
pio run -e face240_wiretest -t upload
pio run -e tftprobe_st7789_rgb_off -t upload
pio run -e tftprobe_st7789_bgr_off -t upload
pio run -e tftprobe_st7789_rgb_on -t upload
pio run -e tftprobe_hybrid_rawinit -t upload
```

Remember that current TFT pins overlap with the OV2640 camera map. Test TFT alone unless the integrated wiring has been changed.

## Windows Local Shell

On Windows local development, prefer PowerShell or CMD commands. Do not default to `bash scripts/*.sh` unless you are intentionally working in a Linux shell or on the target device.

Examples:

```powershell
python -m unittest discover -s tests -v
python -m base_station.monitor.asr_runtime --pattern tired --verbose
python -m base_station.monitor.emotion_runtime --source fake_camera --pattern tired --count 5 --fresh-db --verbose
```
