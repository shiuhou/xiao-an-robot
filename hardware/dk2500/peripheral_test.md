# Peripheral Test Commands

These commands are for DK-2500 bring-up. Adjust device IDs after checking the actual OS.

## USB and PCI

```bash
lsusb
lspci
```

## Audio

```bash
arecord -l
aplay -l
arecord -D default -f cd -d 3 test.wav
aplay test.wav
```

## Camera

```bash
python - <<'PY'
import cv2

cap = cv2.VideoCapture(0)
ok, frame = cap.read()
print("camera_ok=", ok, "shape=", None if frame is None else frame.shape)
cap.release()
PY
```

Repo-level camera check:

```bash
python tools/check_runtime_env.py --check-camera --camera-index 0
python tools/probe_camera.py --camera-index 0 --count 5 --interval 0.2 --verbose
```

## WebSocket Port

```bash
python -m base_station.ws_server.server
python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765
```

In another terminal, send a test command through `/agent`:

```bash
python tools/send_robot_command.py expression caring
python tools/send_robot_command.py motion move_out_of_dock
```

## Runtime Checker

```bash
python tools/check_runtime_env.py
python tools/check_runtime_env.py --json
```

Missing OpenVINO/FunASR/Torch/ONNX Runtime packages are expected warnings until the real model deployment pass.

