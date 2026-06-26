# Xiao An Robot

小安是一個基於 Intel DK-2500 / Core Ultra 基站與 ESP32-S3 機器人本體的桌面智能情感助理。設計重點是「有身體的 Agent」：ESP32-S3 負責低功耗硬件控制與感測串流，DK-2500 負責本地感知與 OpenVINO 推理，Agent / OpenClaw 路徑負責決策、工具調用與互動策略。

目標場景是桌面學習與辦公。小安可以在本地感知疲勞、焦慮或陪伴需求，透過表情屏、短距離安全移動與語音回饋，提供低打擾的主動關懷。

## Start Here

如果你是第一次接手這個 repo，先按這個順序讀：

| 目的 | 先讀 |
| --- | --- |
| 快速理解項目 | 本 README |
| Agent 接手任務 | [docs/agents/README.md](docs/agents/README.md) + [AGENTS.md](AGENTS.md) |
| 看當前進度 | [docs/project_status_2026-06-22.md](docs/project_status_2026-06-22.md) + [docs/project_status_2026-06-25.md](docs/project_status_2026-06-25.md) |
| 改 firmware source | [docs/agents/02_firmware_registry.md](docs/agents/02_firmware_registry.md) + `robot/firmware/platformio.ini` |
| 改 DK-2500 聯調 firmware | [robot/mergetesting/README.md](robot/mergetesting/README.md) + [docs/agents/03_mergetesting_registry.md](docs/agents/03_mergetesting_registry.md) |
| 改 protocol | [docs/protocol.md](docs/protocol.md) + `shared/protocol/*` + firmware `protocol.h` |
| 做架構整理 | [docs/superpowers/specs/2026-06-25-layered-firmware-architecture-design.md](docs/superpowers/specs/2026-06-25-layered-firmware-architecture-design.md) |

## Current Snapshot

Current handoff state:

- Broad hardware and integration baseline: **2026-06-22**, see [docs/project_status_2026-06-22.md](docs/project_status_2026-06-22.md).
- OTA bootstrap addendum: **2026-06-25**, see [docs/project_status_2026-06-25.md](docs/project_status_2026-06-25.md).
- `/control` Phase 1-2 hardening: **2026-06-26**, see [docs/project_status_2026-06-26.md](docs/project_status_2026-06-26.md).
- Architecture optimization proposal: **2026-06-25**, see [layered firmware architecture spec](docs/superpowers/specs/2026-06-25-layered-firmware-architecture-design.md).

Current working direction:

- Keep `robot/firmware` focused on robot-body firmware, isolated hardware bring-up, and reusable modules.
- Keep DK-2500/base-station integration firmware in `robot/mergetesting`.
- Let `robot/mergetesting` copy or sync proven modules from `robot/firmware`, but do not make `robot/firmware` the default DK-2500 demo path.
- Keep hardware bring-up isolated in dedicated PlatformIO envs selected by `build_src_filter`.
- Validate firmware envs one by one with `pio run -e <env>`; broad `pio run` can misrepresent env health.
- Treat `/video`, `/audio`, TFT face, motors, mic, and speaker as staged hardware paths until each peripheral is bench-verified.
- Do not blindly merge remote perception/memory branches into `main`; review them against the current hardware-control route first.

## Status Legend

| Mark | Meaning |
| --- | --- |
| ✅ | Implemented or locally test-backed |
| 🟡 | Test-ready or staged; some hardware/integration work remains |
| 🧪 | Experiment, diagnostic, or prototype path |
| ⬜ | Stub, blocked, or not yet integrated |
| H | Hardware-verified on a real device |
| P | Build/test passed in a local software check |

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

Target runtime loop:

```text
sensor/audio/video input
  -> ESP32-S3 robot body
  -> WebSocket /control /video /audio
  -> DK-2500 perception and ASR
  -> Agent decision
  -> display.expression / motion.execute / audio.play_*
  -> robot status, ack, completion, or error
```

## Repository Layout

Local PlatformIO build output (`.pio/`) is gitignored and safe to delete anytime.

```text
xiao-an-robot/
├── robot/
│   ├── firmware/           # ESP32-S3 robot-body feature tests and reusable modules
│   └── mergetesting/       # DK-2500/base-station integration firmware
├── base_station/           # WebSocket server, perception runtime, ASR/emotion loops
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

## Current Truth Sources

| Topic | Source of truth |
| --- | --- |
| Repo-wide instructions | [AGENTS.md](AGENTS.md) |
| Agent reading order | [docs/agents/README.md](docs/agents/README.md) |
| Firmware envs | `robot/firmware/platformio.ini` |
| Mergetesting envs | `robot/mergetesting/platformio.ini` |
| Firmware file roles | [docs/agents/02_firmware_registry.md](docs/agents/02_firmware_registry.md) |
| Mergetesting file roles | [docs/agents/03_mergetesting_registry.md](docs/agents/03_mergetesting_registry.md) |
| Test matrix | [docs/agents/05_test_matrix.md](docs/agents/05_test_matrix.md) |
| Message contract | [docs/protocol.md](docs/protocol.md) and `shared/protocol/*` |
| Wiring assumptions | [hardware/wiring/esp32_pinout.md](hardware/wiring/esp32_pinout.md) and [docs/hardware_setup.md](docs/hardware_setup.md) |
| Layered refactor direction | [docs/superpowers/specs/2026-06-25-layered-firmware-architecture-design.md](docs/superpowers/specs/2026-06-25-layered-firmware-architecture-design.md) |

## Feature Implementation Map

| Feature area | User value | Main implementation | Status | Verify / next step |
| --- | --- | --- | --- | --- |
| `/control` minimum loop | Robot can connect, receive commands, report status, and execute safe Phase 1-2 commands | `base_station/ws_server/server.py`, `robot/mergetesting/src/app/mergetesting_app.cpp`, `robot/mergetesting/src/services/*`, `robot/mergetesting/src/ws_client.cpp`, `agent/core/gateway.py` | P; hardware H pending | `python -m unittest discover -s tests -p "test_*.py"`; then `pio run -e mergetesting_display_only` |
| Agent command path | Agent can issue expression, motion, and audio commands | `agent/core/brain.py`, `agent/core/gateway.py`, `agent/skills/robot_motion.py`, `tools/send_robot_command.py` | ✅ P | Integration tests and mock robot |
| Robot-body baseline firmware | ESP32 keeps robot-body control separate from DK-2500 demo | `robot/firmware/src/main.cpp`, `ws_client.cpp`, `motor_ctrl.cpp`, `display.cpp` | 🟡 | `cd robot\firmware; pio run -e esp32-s3-devkitc-1` |
| Motor safety and manual bring-up | Safe DRV8833 direction and movement validation | `robot/firmware/src/motor_ctrl.cpp`, `motor_manual_main.cpp`, `motor_bench_once_main.cpp`, `motor_wifi_manual_main.cpp` | ✅ H | `pio run -e motor_manual`; serial WASD or browser AP test |
| Camera + motor AP demo | Local WiFi camera preview and manual driving | `robot/firmware/src/motor_cam_wifi_manual_main.cpp`, `robot/firmware/tools/wifi_camera_viewer.py` | ✅ H baseline | Connect to `XiaoAn-Motor`, open `http://192.168.4.1/` and `http://192.168.4.1:81/stream` |
| `/video` integration | DK-2500 receives JPEG frames for perception | `robot/mergetesting/src/cam_stream.cpp`, `ws_client.cpp`, `base_station/ws_server/server.py` | ✅ P, H 2026-06-25 | `pio run -e mergetesting_cam_only_ota -t upload --upload-port <board-ip>`; verify `runtime/latest.jpg` |
| Face display | 128x160 and 2.4 inch expression output | `display.cpp`, `face240_roboeyes_test.cpp`, `robot_face_9expr_merged_optimized.cpp`, `robot/mergetesting/src/face240_display.cpp` | ✅ / 🟡 | `pio run -e face240_wiretest`; `pio run -e face240_9expr_merged`; `pio run -e mergetesting_face240_only` |
| INMP441 mic | Electrical/RMS validation and future PCM stream | `voice_recognition_test.cpp`, `robot/mergetesting/src/mic_stream.cpp` | 🟡 | `pio run -e voice_recognition_test`; then `pio run -e mergetesting_mic_only` |
| MAX98357A speaker | Local tone and command-triggered sound path | `speaker_amp_test.cpp`, `robot/mergetesting/src/speaker.cpp` | 🟡 | `pio run -e speaker_amp_test`; then mergetesting local sound command |
| OTA bootstrap | Wireless recovery bridge after first USB flash | `ota_bootstrap_main.cpp`, `ota_update.cpp/h`, `config.local.example.h` | ✅ H, 2026-06-25 | `pio run -e ota_bootstrap`; `pio run -e ota_bootstrap_wifi -t upload --upload-port <board-ip>` |
| Active-care perception | Fatigue/emotion trigger for caring response | `base_station/monitor/emotion_runtime.py`, `base_station/perception/*`, Agent brain paths | 🟡 | Mock/OpenCV simulation first; OpenVINO/Qwen still staged |
| Layered firmware architecture | Make envs composable instead of one-off demos | `docs/superpowers/specs/2026-06-25-layered-firmware-architecture-design.md`, `robot/mergetesting/src/app/`, `robot/mergetesting/src/services/` | Phase 1 started | `main.cpp` is now a thin entrypoint; `RobotState`, `StatusService`, `MotionService`, and `CommandRouter` are in `robot/mergetesting/src/services/` |

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

- Main firmware keeps robot-body control and reusable bring-up modules in `robot/firmware`.
- DK-2500 integration firmware lives in `robot/mergetesting` and owns `/control`, `/video`, `/audio` demo behavior.
- Mergetesting Phase 1-2 layering is software-verified: `main.cpp` is a thin Arduino entrypoint, `app/mergetesting_app.cpp` wires runtime setup/loop, and `services/` owns state, status, non-blocking motion, and command routing.
- Robot messages available for integration include `device.hello`, `device.heartbeat`, `device.status`, `motion.completed`, and `error.report`.
- Robot command dispatch supports `system.welcome`, `display.expression`, `motion.execute`, `audio.play_tts`, `audio.play_local`, `config.update`, and `system.shutdown`.
- Motion commands are open-loop and non-blocking in `robot/mergetesting`; `stop` interrupts the active action and reports `motion.completed` with `result: interrupted`.
- Hardware experiments are consolidated under `robot/firmware/platformio.ini`; the old nested `robot/firmware/testing` PlatformIO project has been retired.

## Where To Change Code

| Change type | Work in | Notes |
| --- | --- | --- |
| Single robot-body hardware bring-up | `robot/firmware` | Use a dedicated `*_main.cpp` or test file plus a dedicated env. |
| DK-2500/base-station integration burn | `robot/mergetesting` | Do not add new `/control`, `/video`, or `/audio` integration entrypoints to `robot/firmware`. |
| Proven module reused by integration | validate in `robot/firmware`, then copy/sync minimal module into `robot/mergetesting` | Keep the integration loop in `robot/mergetesting`. |
| Protocol change | `docs/protocol.md`, `shared/protocol/*`, firmware `protocol.h`, mergetesting `protocol.h` | Keep names and payloads aligned. |
| Wiring or env command change | README, [docs/hardware_setup.md](docs/hardware_setup.md), `hardware/wiring/*`, `docs/agents/*` | Update docs with the source change. |
| Architecture refactor | follow the layered firmware spec | Preserve current env names; start new integration behavior in `robot/mergetesting/src/app/` or `robot/mergetesting/src/services/` instead of growing `main.cpp`. |

## Firmware Env Matrix

Run firmware commands from `robot/firmware`.

| Env | Purpose | Main file |
| --- | --- | --- |
| `esp32-s3-devkitc-1` | Robot-body baseline `/control` firmware | `main.cpp` |
| `ota_bootstrap` | USB-flashed WiFi OTA recovery bridge | `ota_bootstrap_main.cpp` |
| `ota_bootstrap_wifi` | Wireless upload target after `ota_bootstrap` is running | `ota_bootstrap_main.cpp` |
| `camtesting` | OV2640 camera capture test | `camtesting_program.cpp` |
| `motor_bench_once` | One-shot motor direction validation | `motor_bench_once_main.cpp` |
| `motor_manual` | Serial WASD motor control | `motor_manual_main.cpp` |
| `motor_wifi_manual` | WiFi AP browser motor control | `motor_wifi_manual_main.cpp` |
| `keepfacecenter` | Camera + motor pulse centering demo | `keep_face_center_test.cpp` |
| `serialqrservo` | ESP32 JPEG serial stream + PC QR visual servo | `serial_qr_servo_main.cpp` |
| `motor_cam_wifi_manual` | WiFi motor + camera stream + isolated QR test route | `motor_cam_wifi_manual_main.cpp` |
| `redtracker` | On-device red target tracker | `red_circle_tracker_test.cpp` |
| `serialredtracker` | Serial red target tracker | `serial_red_tracker_test.cpp` |
| `display_test` | 128x160 ST7735 TFT test | `tft_test.cpp` |
| `face240_roboeyes` | 2.4 inch raw ST7789 RoboEyes face demo | `face240_roboeyes_test.cpp` |
| `face240` | Alias of `face240_roboeyes` | `face240_roboeyes_test.cpp` |
| `face240_integrated` | Alias of `face240_wiretest` | `face240_wire_test.cpp` |
| `face240_wiretest` | 2.4 inch ST7789 color/wiring test | `face240_wire_test.cpp` |
| `face240_legacy` | Legacy GPIO9-12 harness only | `face240_wire_test.cpp` |
| `display_test_legacy` | Legacy 128x160 ST7735 harness | `tft_test.cpp` |
| `face240_9expr_merged` | 2.4 inch nine-expression product face path | `robot_face_9expr_merged_optimized.cpp` |
| `tftprobe_hybrid_rawinit` | ST7789 hybrid raw-init diagnostic | `tft_espi_probe.cpp` |
| `voice_recognition_test` | INMP441 I2S RMS/voice activity test, not ASR | `voice_recognition_test.cpp` |
| `speaker_amp_test` | MAX98357A I2S speaker amp tone test | `speaker_amp_test.cpp` |
| `esp32-s3-integrated_legacy` | Historical firmware-side DK-2500 snapshot; do not use for new burns | `integrated_main.cpp` |

DK-2500/base-station integration envs live in `robot/mergetesting`.

| Env | Purpose |
| --- | --- |
| `mergetesting` | Integration baseline; default feature mix |
| `mergetesting_display_only` | Phase 1-2 `/control`, display, motor, speaker path |
| `mergetesting_display_only_ota` | OTA upload target for the Phase 1-2 `/control` firmware; build/upload-ready, H pending |
| `mergetesting_face240_only` | Phase 2 2.4 inch face path |
| `mergetesting_cam_only` | Phase 3 OV2640 JPEG `/video` path; camera-only QVGA smoke target with motor/speaker/mic disabled |
| `mergetesting_cam_only_ota` | OTA upload target for the camera-only integration firmware; hardware-verified 2026-06-25 |
| `mergetesting_mic_only` | INMP441 PCM `/audio` path |
| `mergetesting_base64_video` | `/video` base64 fallback |

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_display_only_ota
pio run -e mergetesting_face240_only
pio run -e mergetesting_cam_only
pio run -e mergetesting_cam_only_ota
pio run -e mergetesting_mic_only
```

Related face display tools:

- `robot/firmware/tools/face240_preview.html`: browser preview of the 320x240 face design.
- `robot/firmware/tools/test_face240_raw_dirty_rect.py`: structure check for `experiments/face240_raw_design_test.cpp`.

Build examples:

```powershell
cd robot\firmware
pio run -e esp32-s3-devkitc-1
pio run -e ota_bootstrap
pio run -e motor_manual
pio run -e motor_cam_wifi_manual
pio run -e face240_integrated
pio run -e face240_wiretest
pio run -e face240_9expr_merged
pio run -e voice_recognition_test
pio run -e speaker_amp_test
```

OTA bootstrap:

- Keep real WiFi and OTA credentials in ignored `robot/firmware/src/config.local.h`; `config.local.example.h` documents the keys.
- First flash the bridge over USB: `pio run -e ota_bootstrap -t upload --upload-port COMxx`.
- Expected serial behavior: `[OTA_BOOT] WiFi connected IP=...`, then `[OTA] Ready hostname=xiao-an-esp32 auth=...`, followed by 5s `alive` logs.
- After the bridge is running on WiFi, upload wirelessly with `pio run -e ota_bootstrap_wifi -t upload --upload-port <board-ip>`.
- `ota_bootstrap_wifi` only rebuilds and uploads the bootstrap firmware. To wirelessly upload another functional env, create or use that env's own OTA-enabled upload target; the firmware being uploaded must start WiFi, call ArduinoOTA setup, and keep calling the OTA loop after boot. Otherwise OTA is lost after that firmware reboots.
- Hardware-verified 2026-06-25 on `COM19` using a Windows hotspot: ESP32 IP `192.168.137.197`, wireless upload returned espota `Result: OK`. See [docs/project_status_2026-06-25.md](docs/project_status_2026-06-25.md).

WiFi manual demos:

- `motor_wifi_manual`: connect to `XiaoAn-Motor` / `12345678`, open `http://192.168.4.1/`.
- `motor_cam_wifi_manual`: connect to `XiaoAn-Motor` / `12345678`, open `http://192.168.4.1/`; MJPEG stream is also exposed at `http://192.168.4.1:81/stream`.

## Hardware Map

Current firmware pin assumptions are documented in [hardware/wiring/esp32_pinout.md](hardware/wiring/esp32_pinout.md).

Important notes:

- Motor bring-up uses DRV8833: left IN1/IN2 = GPIO1/GPIO2, right IN1/IN2 = GPIO3/GPIO48.
- OV2640 uses the GOOUUU ESP32-S3-CAM v1.5 pin map in `cam_stream.cpp` and camera test files.
- Integrated TFT wiring: SCK=GPIO14, MOSI=GPIO21, CS=GPIO42, DC=GPIO43, RST=GPIO44, LED/BL tied to 3V3 (`TFT_BL=-1`). Source: `board_pins.h`, `hardware_pins.h`, and [hardware/wiring/esp32_pinout.md](hardware/wiring/esp32_pinout.md).
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
python tools\send_robot_command.py local care_01
python tools\send_robot_command.py tts --text "小安，提醒我休息一下"
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
robot/mergetesting -> base_station WebSocket -> Agent decision -> expression/motion/audio command -> robot feedback
```

The first reliable integration contract is:

```text
device.hello -> system.welcome -> device.status -> motion.execute -> command.ack -> motion.completed or error.report -> device.status
```

## Development Direction

1. Keep tightening the visible `/control` minimum loop on real hardware now that the mergetesting app/service split is in place.
2. Validate physical peripherals in this order: motor safety, TFT expression, OV2640 capture, dock limit switch, speaker amp, INMP441 mic.
3. Preserve the low-rate `/video` route in `robot/mergetesting`; the camera-only OTA route has returned JPEG frames to the base station and should remain the video regression target.
4. Keep `/audio`, real ASR, and TTS playback as the second integration layer in `robot/mergetesting` + `base_station`.
5. Replace mock perception with OpenVINO/OpenFace/Qwen paths only after live control is observable and safe.
6. Continue the layered migration from the landed mergetesting `app/` + `services/` slice toward reusable `hal/transport/protocol` modules.
7. Review remote perception/memory branches deliberately before merging into `main`.

## Documentation Health Notes

This repo has both hand-written docs and generated/dated snapshots. Prefer this order when documents disagree:

1. Live source and `platformio.ini`.
2. [AGENTS.md](AGENTS.md) for repo rules.
3. Latest dated status docs.
4. `docs/agents/*` registries.
5. Older status snapshots and archived docs.

Known dated docs:

- [docs/project_status_2026-06-22.md](docs/project_status_2026-06-22.md) is still the broad hardware/integration baseline.
- [docs/project_status_2026-06-25.md](docs/project_status_2026-06-25.md) is an OTA bootstrap addendum, not a full replacement.
- [docs/agents/_generated/file_inventory.md](docs/agents/_generated/file_inventory.md) is generated and may change after `python tools/generate_agent_registry.py`.

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
- `command.ack`
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
- Real `config.local.h` files.
- Virtual environments.
- `node_modules`.
- Downloaded model files.
- `.pio` / PlatformIO generated build state.
- User private profile data.

Use `.env.example`, `base_station/config.example.yaml`, `robot/firmware/src/config.local.example.h`, `robot/mergetesting/src/config.local.example.h`, and `agent/data/schema.sql` as templates.

## License

MIT License. See [LICENSE](LICENSE).
