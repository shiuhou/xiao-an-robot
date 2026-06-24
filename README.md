# Xiao An Robot

小安是一個基於 Intel DK-2500 / Core Ultra 基站與 ESP32-S3 機器人本體的桌面智能情感助理。設計重點是「有身體的 Agent」：ESP32-S3 負責低功耗硬體控制與感測串流，DK-2500 負責本地感知與 OpenVINO 推理，Agent / OpenClaw 路徑負責決策、工具調用與互動策略。

目標場景是桌面學習與辦公。小安可以在本地感知疲勞、焦慮或陪伴需求，透過表情屏、短距離安全移動與語音回饋，提供低打擾的主動關懷。

## Current Snapshot

Updated snapshot: **2026-06-22**. Detailed handoff: [docs/project_status_2026-06-22.md](docs/project_status_2026-06-22.md).

Current working direction:

- Keep `robot/firmware/src/main.cpp` as the main `/control` integration path.
- Keep hardware bring-up isolated in dedicated PlatformIO envs selected by `build_src_filter`.
- Validate firmware envs one by one with `pio run -e <env>`; broad `pio run` can misrepresent env health.
- Treat `/video`, `/audio`, TFT face, motors, mic, and speaker as staged hardware paths until each peripheral is bench-verified.
- Do not blindly merge remote perception/memory branches into `main`; review them against the current hardware-control route first.

## Core Architecture

```text
Robot Body (ESP32-S3)
  - camera / mic / display / motors / servos / speaker
  - streams sensor data and executes commands

Base Station (Intel DK-2500 / Core Ultra)
  - WebSocket server
  - OpenVINO / local perception
  - ASR / VAD / TTS
  - SQLite local memory

Agent Layer (OpenClaw + LLM)
  - understands intent
  - plans actions
  - calls skills/tools
  - returns text, emotion, and robot commands
```

Heavy perception and reasoning stay on the DK-2500. The robot body should stay light, observable, and safe.

## Repository Layout

Local PlatformIO build output (`.pio/`) is gitignored and safe to delete anytime.

```text
xiao-an-robot/
├── robot/                  # ESP32-S3 firmware and isolated hardware bring-up envs
│   └── firmware/
├── base_station/           # DK-2500 WebSocket server, perception runtime, ASR/emotion loops
│   ├── ws_server/
│   ├── perception/
│   └── monitor/
├── agent/                  # Agent brain, gateway, skills, memory/context shell
│   ├── core/
│   ├── skills/
│   └── data/
├── shared/                 # Protocol schema, constants, and examples
├── frontend/               # Early desktop UI placeholder
├── hardware/               # BOM, wiring, DK-2500, shell, and dock notes
├── docs/                   # Architecture, protocol, deployment, status, troubleshooting
├── tests/                  # Unit/integration tests and mock robot
├── tools/                  # Local operation and probe scripts
└── scripts/                # Startup/setup helper scripts
```

## What Works Now

Base station and Agent:

- WebSocket `/control`, `/agent`, `/audio`, and `/video` routes exist.
- `tests/mocks/mock_robot.py` can connect to `/control`, send device messages, and receive commands.
- `RobotGateway` and `RobotMotionSkill` can send expression, motion, and TTS command messages through `/agent`.
- `care_for_user()` produces the core demo sequence.
- `XiaoAnBrain` routes ASR, emotion, frontend, and OpenClaw/tool-call style events through tested MVP paths.
- `EmotionDB`, `EmotionEventLoop`, and `emotion_runtime` support fake/mock/OpenCV-source active-care simulation.
- Qwen/VLM gate and wrapper paths exist; real OpenVINO Qwen generation remains staged.

ESP32-S3 firmware:

- Main firmware has a `/control` WebSocket client in `ws_client.cpp/.h`.
- Robot messages implemented in the main firmware include `device.hello`, `device.heartbeat`, `device.status`, `motion.completed`, and `error.report`.
- Robot command dispatch includes `system.welcome`, `display.expression`, `motion.execute`, `audio.play_tts`, `audio.play_local`, `config.update`, and `system.shutdown`.
- Audio commands intentionally return `AUDIO_UNSUPPORTED` until MAX98357A/TTS playback is integrated.
- Hardware experiments are now consolidated under `robot/firmware/platformio.ini`; the old nested `robot/firmware/testing` PlatformIO project has been retired.

## Firmware Env Matrix

Run firmware commands from `robot/firmware`.

| Env | Purpose | Main file |
| --- | --- | --- |
| `esp32-s3-devkitc-1` | Main `/control` firmware | `main.cpp` |
| `camtesting` | OV2640 camera capture test | `camtesting_program.cpp` |
| `motor_bench_once` | One-shot motor direction validation | `motor_bench_once_main.cpp` |
| `motor_manual` | Serial WASD motor control | `motor_manual_main.cpp` |
| `motor_wifi_manual` | WiFi AP browser motor control | `motor_wifi_manual_main.cpp` |
| `keepfacecenter` | Camera + motor pulse centering demo | `keep_face_center_test.cpp` |
| `serialqrservo` | ESP32 JPEG serial stream + PC QR visual servo | `serial_qr_servo_main.cpp` |
| `motor_cam_wifi_manual` | WiFi motor + camera stream + on-device QR overlay demo | `motor_cam_wifi_manual_main.cpp` |
| `redtracker` | On-device red target tracker | `red_circle_tracker_test.cpp` |
| `serialredtracker` | Serial red target tracker | `serial_red_tracker_test.cpp` |
| `display_test` | 128x160 ST7735 TFT test | `tft_test.cpp` |
| `face240_roboeyes` | 2.4 inch raw ST7789 robo-eyes face demo (canonical) | `face240_roboeyes_test.cpp` |
| `face240` | Alias of `face240_roboeyes` | `face240_roboeyes_test.cpp` |
| `face240_integrated` | Alias of `face240_wiretest` | Integrated harness wiring check |
| `face240_wiretest` | 2.4 inch ST7789 color/wiring test | `face240_wire_test.cpp` |
| `face240_legacy` | Legacy GPIO9–12 harness only | `face240_wire_test.cpp` |
| `display_test_legacy` | Legacy 128x160 ST7735 harness | `tft_test.cpp` |
| `face240_9expr_merged` | 2.4 inch 9-expression inner-face demo (product path) | `robot_face_9expr_merged_optimized.cpp` |
| `tftprobe_hybrid_rawinit` | ST7789 hybrid raw-init probe | `tft_espi_probe.cpp` |
| `voice_recognition_test` | INMP441 I2S RMS/voice activity test | `voice_recognition_test.cpp` |
| `speaker_amp_test` | MAX98357A I2S speaker amp tone test | `speaker_amp_test.cpp` |

Related face display tools:

- `robot/firmware/tools/face240_preview.html`: browser preview of the 320x240 face design.
- `robot/firmware/tools/test_face240_raw_dirty_rect.py`: structure check for `experiments/face240_raw_design_test.cpp`.

Build examples:

```powershell
cd robot\firmware
pio run -e esp32-s3-devkitc-1
pio run -e motor_manual
pio run -e motor_cam_wifi_manual
pio run -e face240_integrated
pio run -e face240_wiretest
pio run -e face240_9expr_merged
pio run -e voice_recognition_test
pio run -e speaker_amp_test
```

WiFi manual demos:

- `motor_wifi_manual`: connect to `XiaoAn-Motor` / `12345678`, open `http://192.168.4.1/`.
- `motor_cam_wifi_manual`: connect to `XiaoAn-Motor` / `12345678`, open `http://192.168.4.1/`; MJPEG stream is also exposed at `http://192.168.4.1:81/stream`.

## Hardware Map

Current firmware pin assumptions are documented in [hardware/wiring/esp32_pinout.md](hardware/wiring/esp32_pinout.md).

Important notes:

- Motor bring-up uses DRV8833: left IN1/IN2 = GPIO1/GPIO2, right IN1/IN2 = GPIO3/GPIO48.
- OV2640 uses the GOOUUU ESP32-S3-CAM v1.5 pin map in `cam_stream.cpp` and camera test files.
- Integrated TFT wiring (default): SCK=GPIO14, MOSI=GPIO21, CS=GPIO42, DC=GPIO43, RST=GPIO44, LED/BL tied to 3V3 (`TFT_BL=-1`). Source: `board_pins.h`, [hardware/wiring/esp32_pinout.md](hardware/wiring/esp32_pinout.md).
- Legacy TFT bench (`face240_legacy`, `display_test_legacy`) uses GPIO9/10/11/12 and must not share a harness with OV2640.
- INMP441 test uses BCLK GPIO39, WS GPIO40, DIN GPIO41.
- MAX98357A test uses BCLK GPIO35, LRC GPIO36, DIN GPIO37.
- Limit switches are disabled in firmware during motor bench bring-up (`-1`) until final GPIOs are assigned.

## Quick Start

### Python Test Suite

From the repository root:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

The last recorded full local verification on 2026-06-18 was:

```text
Ran 325 tests
OK
```

Run a current environment check:

```powershell
python tools/check_runtime_env.py
python tools/check_runtime_env.py --check-camera
```

### Start Base Station

```powershell
python -m venv base_station\venv
base_station\venv\Scripts\python -m pip install -r base_station\requirements.txt
base_station\venv\Scripts\python -m base_station.ws_server.server
```

### Start Mock Robot

```powershell
python tests\mocks\mock_robot.py --host 127.0.0.1 --port 8765
```

### Send Robot Commands

```powershell
python tools\send_robot_command.py expression caring
python tools\send_robot_command.py motion move_out_of_dock
python tools\send_robot_command.py tts "你已經工作很久了，休息一下吧。"
```

### Run Active-Care Simulation

Neutral case:

```powershell
python -m base_station.monitor.emotion_runtime --source fake_camera --model-backend mock --enable-vlm-gate --vlm-backend qwen_vl --pattern neutral --count 3 --fresh-db --verbose
```

Tired case:

```powershell
python -m base_station.monitor.emotion_runtime --source fake_camera --model-backend mock --enable-vlm-gate --vlm-backend qwen_vl --pattern tired --count 3 --fresh-db --verbose
```

## Product Routes

Target product routes:

1. Daily voice interaction: user speech -> VAD/ASR -> Agent/tool call -> TTS response.
2. Visual active care: low-rate camera perception -> fatigue/emotion trigger -> Agent decision -> caring expression and short safe movement.
3. Quick companion request: local ASR text trigger -> immediate expression/action -> richer reply generated in the background.

Current demo priority:

```text
Perception trigger -> Agent decision -> caring expression -> short safe movement -> robot feedback
```

## Development Direction

1. Finish the visible `/control` minimum loop on real hardware.
2. Validate physical peripherals in this order: motor safety, TFT expression, OV2640 capture, dock limit switch, speaker amp, INMP441 mic.
3. Add low-rate `/video` only after `/control` is stable.
4. Keep `/audio`, real ASR, and TTS playback as the second integration layer.
5. Replace mock perception with OpenVINO/OpenFace/Qwen paths only after live control is observable and safe.
6. Review remote perception/memory branches deliberately before merging into `main`.

## Protocol

See [docs/protocol.md](docs/protocol.md).

Main channels:

- `/control`: bidirectional JSON command channel.
- `/audio`: robot-to-base-station PCM audio stream.
- `/video`: robot-to-base-station JPEG frame stream.
- `/agent`: agent-to-base-station command route used by local skills/tools.

Main robot-facing commands:

- `display.expression`
- `motion.execute`
- `audio.play_tts`
- `audio.play_local`
- `config.update`
- `system.shutdown`

Main robot-to-base messages:

- `device.hello`
- `device.heartbeat`
- `device.status`
- `motion.completed`
- `error.report`

## Privacy Model

- Raw camera frames and microphone audio should stay on the local robot/base-station system.
- DK-2500 performs local perception and converts raw data into structured labels or summaries.
- Cloud LLM/OpenClaw should receive text summaries, state labels, and user-approved context, not raw audio/video.
- Local SQLite stores emotion history and interaction metadata.

## Files That Should Not Be Committed

- Real logs.
- SQLite databases.
- Local `.env` files and API keys.
- Virtual environments.
- `node_modules`.
- Downloaded model files.
- `.pio` / PlatformIO generated build state.
- User private profile data.

Use `.env.example`, `base_station/config.example.yaml`, and `agent/data/schema.sql` as templates.

## License

MIT License. See [LICENSE](LICENSE).
