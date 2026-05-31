# Peripheral Test Commands

These commands are placeholders for DK2500 bring-up. Adjust names and device ids after checking the actual OS.

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

## WebSocket Port

```bash
python -m base_station.ws_server.server
python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765
```

