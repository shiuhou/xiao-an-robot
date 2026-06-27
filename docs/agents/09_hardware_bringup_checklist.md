# Hardware Bring-up Checklist - 2026-06-26

Scope: `robot/mergetesting` DK-2500/base-station integration firmware only.
Do not burn new `/control`, `/video`, or `/audio` integration entrypoints from
`robot/firmware`.

## Local Config

Before any upload, check `robot/mergetesting/src/config.local.h` exists locally
and is not staged.

Create it by copying `robot/mergetesting/src/config.local.example.h` to
`robot/mergetesting/src/config.local.h`. The local file is ignored by Git and
must not be committed.

Required values:

```cpp
#define MERGETEST_WIFI_SSID "<lab-wifi>"
#define MERGETEST_WIFI_PASSWORD "<lab-wifi-password>"
#define MERGETEST_BASE_STATION_IP "<DK-2500-LAN-IP>"
#define MERGETEST_BASE_STATION_PORT 8765
#define MERGETEST_DEVICE_ID "xiaoan_robot_01"
```

First check if it fails: wrong WiFi band/password or DK-2500 IP not reachable
from the ESP32 network. ESP32 and DK-2500 must be on the same LAN.

## Base Station

Run from repo root:

```powershell
.venv\Scripts\python -m base_station.ws_server.server
```

Expected base-station logs:

```text
Starting Xiao An WebSocket server on 0.0.0.0:8765
New connection on path: /control
Robot connected: xiaoan_robot_01
Command ack: type=... status=ok
Video meta: frame_id=... 320x240
Audio meta: chunk_id=... format=pcm_s16le sample_rate=16000 channels=1
```

First check if it fails: Windows firewall or the ESP32 is pointing at the wrong
`MERGETEST_BASE_STATION_IP`.

## Phase 1-2 Control, Display, Motion, Speaker

Firmware env: `mergetesting_display_only`

Build and upload:

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_display_only -t upload --upload-port COMxx
pio device monitor -b 115200
```

Expected serial logs:

```text
[Main] Xiao An merge-testing firmware robot-fw-0.1
[WiFi] Connected IP=...
[WS] Connecting control ws://<DK-2500-IP>:8765/control
[WS] Control connected: ...
[WS] Sent device.hello device_id=xiaoan_robot_01
[WS] Rx control: system.welcome
[WS] Heartbeat uptime_ms=... busy=false
[WS] command.ack display.expression -> ok
[Motion] started action=move_out_of_dock action_id=...
[Motion] completed action=move_out_of_dock action_id=... result=success
[Speaker] play_local care_01
[Speaker] tts mock ... preview=...
```

Expected base-station logs:

```text
Robot connected: xiaoan_robot_01
Command ack: type=display.expression status=ok
Command ack: type=motion.execute status=ok
Motion completed: <action_id> -> success
Command ack: type=audio.play_local status=ok
Command ack: type=audio.play_tts status=ok
```

Command checks from repo root:

```powershell
.venv\Scripts\python tools\send_robot_command.py --device-id xiaoan_robot_01 expression idle
.venv\Scripts\python tools\send_robot_command.py --device-id xiaoan_robot_01 expression caring
.venv\Scripts\python tools\send_robot_command.py --device-id xiaoan_robot_01 motion move_out_of_dock --speed 0.2 --distance-cm 2 --timeout-ms 500
.venv\Scripts\python tools\send_robot_command.py --device-id xiaoan_robot_01 motion stop
.venv\Scripts\python tools\send_robot_command.py --device-id xiaoan_robot_01 motion move_back_to_dock --speed 0.2 --timeout-ms 500
.venv\Scripts\python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

Linux shell equivalent:

```bash
.venv/bin/python -m base_station.ws_server.server
.venv/bin/python tools/send_robot_command.py --device-id xiaoan_robot_01 expression idle
.venv/bin/python tools/send_robot_command.py --device-id xiaoan_robot_01 expression caring
.venv/bin/python tools/send_robot_command.py --device-id xiaoan_robot_01 motion move_out_of_dock --speed 0.2 --distance-cm 2 --timeout-ms 500
.venv/bin/python tools/send_robot_command.py --device-id xiaoan_robot_01 motion stop
.venv/bin/python tools/send_robot_command.py --device-id xiaoan_robot_01 motion move_back_to_dock --speed 0.2 --timeout-ms 500
.venv/bin/python tools/send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

OpenClaw real-robot smoke after the `/control` route is stable:

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
XIAO_AN_OPENCLAW_GATEWAY_TIMEOUT_SEC=90 \
.venv/bin/python tools/send_frontend_message.py "让小安用 caring 表情出来陪我一下" --verbose
```

First checks if it fails:

- No `Control connected`: check WiFi credentials, base-station IP, port 8765, and firewall.
- No `device.hello`: check `/control` path and WebSocket server is running.
- Command reaches base station but not robot: check `Robot connected` session still exists.
- Motion tests must use low speed, short distance, and short timeout. Real motor
  tests need external motor power, common ground, and the robot lifted or placed
  in a safe test position.
- Motion does not move: check DRV8833 wiring L=GPIO1/GPIO2, R=GPIO3/GPIO48, battery, and motor direction macros.
- Speaker silent: check MAX98357A BCLK=35, LRC=36, DIN=37, 5V/3V3 power, and shared ground.

## Face240 Display

Firmware env: `mergetesting_face240_only`

Build and upload only after Phase 1-2 control works:

```powershell
cd robot\mergetesting
pio run -e mergetesting_face240_only
pio run -e mergetesting_face240_only -t upload --upload-port COMxx
pio device monitor -b 115200
```

Expected serial logs:

```text
[Face240] ST7789 raw init start
[Face240] ST7789 raw init done
[Face240] merged 9 inner expressions - no shell
[Face240] fps=...
[WS] command.ack display.expression -> ok
```

Expected hardware result: 2.4 inch ST7789 face changes on `expression caring`.

First check if it fails: verify TFT shared SPI wiring SCLK=14, MOSI=21, CS=42,
DC=43, RST=44, BL tied to 3V3 (`TFT_BL=-1`), then check the panel is not the
legacy GPIO9-12 bench harness.

## Camera Video

Firmware env: `mergetesting_cam_only`

Use `mergetesting_cam_only` first. Do not burn full `mergetesting` for the
first video check, and do not connect Qwen/OpenVINO to this smoke test.

Build and upload:

```powershell
cd robot\mergetesting
pio run -e mergetesting_cam_only
pio run -e mergetesting_cam_only -t upload --upload-port COMxx
pio device monitor -b 115200
```

Expected serial logs:

```text
[Cam] Init OV2640 QVGA320 JPEG q=12 interval=1000ms
[Cam] Camera ready QVGA320
[WS] Video channel connected: ...
[Cam] frame #... 320x240 len=... ok=...
```

Expected base-station result:

```text
New connection on path: /video
Video stream connected
Video meta: frame_id=... 320x240
```

Expected file:

```powershell
Get-Item runtime\latest.jpg
```

`runtime/latest.jpg` timestamp should update once per second while the camera is
streaming, and the file should have valid JPEG SOI/EOI bytes.

Heartbeat on `/control` should continue while `/video` is connected.

First check if it fails: confirm the OV2640 FPC and camera power, then check the
camera-only env is used. Do not diagnose camera on `mergetesting_display_only`.

## Microphone PCM

Firmware env: `mergetesting_mic_only`

Use `mergetesting_mic_only` first. Do not connect SenseVoice, Silero-VAD, or any
ASR/VAD pipeline to this smoke test.

Build and upload:

```powershell
cd robot\mergetesting
pio run -e mergetesting_mic_only
pio run -e mergetesting_mic_only -t upload --upload-port COMxx
pio device monitor -b 115200
```

Expected serial logs:

```text
[Mic] INMP441 ready BCLK=39 WS=40 DIN=41
[WS] Audio channel connected: ...
[WS] Heartbeat uptime_ms=... busy=false
```

Expected base-station logs and files:

```text
New connection on path: /audio
Audio stream connected
Audio meta: chunk_id=... format=pcm_s16le sample_rate=16000 channels=1
```

```powershell
Get-Content runtime\audio_stats.json
Get-Item runtime\latest_audio.pcm
```

`audio_stats.json` should show increasing `chunks` and `bytes`. The PCM file is
bounded to 5 seconds of 16 kHz mono signed 16-bit audio.

Control commands should still return `command.ack` while `/audio` is streaming.

First check if it fails: verify INMP441 BCLK=39, WS=40, DIN=41, 3V3, GND, and
that `/audio` is connected. Firmware intentionally does not read/send mic data
when `/audio` is disconnected.

## Full Env Policy

Build-only check:

```powershell
cd robot\mergetesting
pio run -e mergetesting
```

Do not use full `mergetesting` as the first hardware burn. The first 30-minute
bring-up should stay split by env so one hardware fault cannot mask the other
channels:

1. `mergetesting_display_only`
2. `mergetesting_cam_only`
3. `mergetesting_mic_only`
4. `mergetesting_face240_only` if the 2.4 inch display is connected
