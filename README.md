# Xiao An Robot

小安是一個基於 Intel Core Ultra / Intel DK-2500 的桌面智能情感助理。它不是單純的聊天機器人，也不是只會賣萌的桌面玩具，而是一個「有身體的 Agent」：基站負責本地感知與推理，OpenClaw/LLM 負責決策，ESP32-S3 機器人負責表情、移動與語音輸出。

項目目標是在桌面學習和辦公場景中，讓小安能主動感知使用者疲勞、焦慮或需要陪伴的狀態，並以實體機器人的方式走出 Dock、顯示表情、播放語音，提供低打擾的情感關懷與效率輔助。

## Core Idea

小安的核心設計是「算力分離」：

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

The robot body should stay light and low-power. Heavy work such as face emotion recognition, ASR, VAD, Qwen/OpenVINO inference, context assembly, and decision making belongs on the Intel base station.

## Product Experience

小安最終要支援三條並行鏈路：

1. **日常語音交互**
   - 使用者主動說話，例如「幫我記一下明天下午有會」。
   - 麥克風音訊進入基站，經 VAD/ASR 轉文字。
   - OpenClaw/LLM 理解意圖並調用工具，例如日程、筆記、查詢。
   - 機器人在 Dock 內原地用 TTS 回覆。

2. **視覺主動關懷**
   - 使用者不需要喚醒小安。
   - 攝像頭低頻持續感知，基站本地計算情緒、疲勞、姿態等狀態。
   - SQLite 記錄情緒趨勢，超過閾值時觸發 Agent。
   - 機器人顯示 caring 表情、駛出 Dock，播放關懷語音。

3. **快捷陪伴請求**
   - 使用者突然說「我有點累」「陪陪我」。
   - 本地 ASR 文本先走快速關鍵詞/情緒觸發。
   - 機器人立即做出表情和動作，同時後台請 OpenClaw/LLM 生成更個性化回覆。

## Repository Layout

```text
xiao-an-robot/
├── robot/                  # ESP32-S3 firmware: motion, display, camera, mic, speaker
├── base_station/           # Intel DK-2500 Python services and perception runtime
│   ├── ws_server/          # WebSocket /control, /audio, /video, /agent routes
│   ├── perception/         # camera, emotion, ASR, VAD, TTS, Qwen/OpenVINO shells
│   └── monitor/            # emotion runtime, event loop, SQLite emotion DB
├── agent/                  # runtime/agent-side code and skills
│   ├── core/               # gateway, brain/runtime, memory/context placeholders
│   ├── skills/             # emotion monitor, robot motion, calendar, reports, etc.
│   └── data/               # SQLite schema and migrations
├── shared/                 # shared protocol constants, schema, examples
├── frontend/               # Electron base-station UI placeholder
├── hardware/               # BOM, wiring, DK2500, mechanical, dock notes
├── docs/                   # architecture, protocol, deployment, troubleshooting
├── tests/                  # unit/integration tests and mock robot
├── tools/                  # local test and operation scripts
└── scripts/                # setup/start helper scripts
```

## Current Status

Updated snapshot: **2026-06-18**. See [docs/project_status_2026-06-18.md](docs/project_status_2026-06-18.md) for the detailed handoff.

已經比較扎實的部分：

- WebSocket `/control`, `/agent`, `/audio`, and `/video` routes exist on the base station.
- `tests/mocks/mock_robot.py` can connect to `/control`, send `device.hello` / `device.heartbeat`, and receive commands.
- ESP32 `/control` firmware now sends `device.hello`, `device.heartbeat`, `device.status`, `motion.completed`, and `error.report`.
- Agent-side `RobotGateway` can send robot commands through `/agent`.
- `RobotMotionSkill` supports expression, motion, TTS command forwarding, and `care_for_user()`.
- `XiaoAnBrain` routes ASR, emotion, frontend, and OpenClaw/tool-call style events through a tested MVP path.
- `CompanionRequestSkill`, `asr_runtime`, and `asr_emotion_trigger` are now present and covered by tests.
- `EmotionDB` stores emotion samples in SQLite and summarizes recent history.
- `EmotionEventLoop` wraps perception samples into `emotion.sample` events.
- Fake camera / fake face emotion / fake Qwen VL paths exist for local simulation.
- `VLMTriggerGate` decides when to run the heavier VLM path.
- `emotion_runtime` can run the visual active-care MVP with fake/mock/OpenCV-source paths.
- ESP32 firmware has isolated bring-up environments for motor, camera, QR visual servo, TFT, INMP441 voice activity, and speaker amp tests.
- The main firmware build and Python test suite passed after the `/control` feedback update.

Still incomplete or placeholder:

- Real OpenVINO face emotion postprocessing is not finished on `main`.
- Qwen2.5-VL OpenVINO runner is still a placeholder on `main`.
- Real SenseVoice/FunASR, Silero-VAD, TTS playback, audio emotion, and head pose modules still need production wiring.
- ESP32 `/video` and `/audio` transport are not yet integrated into the main firmware loop.
- TFT, motor, camera, microphone, and speaker have isolated test firmware, but the physical full-body integration still needs bench validation.
- WiFi credentials and base-station IP are still hardcoded placeholders in firmware and should move to local config/NVS before real deployment.
- Frontend UI is still an early placeholder.
- GitHub has unmerged remote branches for ASR/memory and OpenFace/OpenVINO perception work; they should be reviewed and merged deliberately rather than blindly merged into `main`.

## Hardware Plan

Confirmed or planned hardware:

| Part | Suggested / Known Model | Purpose |
| --- | --- | --- |
| Base station | Intel DK-2500 / Core Ultra | Local AI, OpenVINO, WebSocket server, Agent runtime |
| Robot MCU | ESP32-S3 DevKitC-1 | Robot-side controller |
| Camera | OV2640 + 24-pin FPC adapter | Robot image/video capture |
| Microphone | INMP441 | I2S voice capture |
| Display | Small TFT IPS, e.g. 1.69 inch 240x280 | Face/expression display |
| Motors | N20 gear motor x2, 3V-6V, about 150-200 RPM | Differential drive |
| Motor driver | DRV8833 | Dual motor control |
| Servos | SG90 x2 | Ears/head movement |
| Speaker amp | MAX98357A | I2S audio output |
| Speaker | 8 ohm 1W small speaker | TTS/audio playback |
| Battery | 3.7V Li-ion/LiPo with protection | Robot power |
| Charging | Wireless charging transmitter + receiver | Dock charging |
| Limit switches | Micro switches x2 | Dock detection / safety |
| Mechanical | 3D-printed chassis, upper shell, Dock | Prototype body |

Important hardware notes:

- The project uses a **wireless charging Dock**, not a TP4056 wired charging-first design.
- ESP32-S3 DevKitC-1 does not have a camera FPC socket, so OV2640 needs the 24-pin FPC adapter and manual GPIO wiring.
- Do not assemble the final shell first. Validate every peripheral on the bench before mounting.
- For the first physical demo, prioritize: ESP32 boot, camera test, motor movement, dock limit switch, TFT expression, then speaker/mic.

## Hardware Bring-Up Order

Recommended order for the hardware owner:

1. ESP32-S3 bare-board serial/upload test.
2. OV2640 camera test through the FPC adapter.
3. Wireless charging module standalone test with a multimeter and dummy load.
4. DRV8833 + N20 motor test without wheels.
5. Wheel movement test on a temporary chassis.
6. Rear limit switch test for Dock detection.
7. Simple Dock prototype with guide rails and wireless coil alignment.
8. TFT static expression test.
9. SG90 servo movement test.
10. MAX98357A + speaker playback test.
11. INMP441 recording test.
12. Integrate into a 3D-printed chassis only after the bench tests pass.

## Quick Start

### Run Tests

The bundled runtime in this environment does not include `pytest`, but standard `unittest` works:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Expected current result from the 2026-06-18 local verification:

```text
Ran 325 tests
OK
```

### Start Base Station

Windows PowerShell/CMD, run from the repository root:

```powershell
python -m venv base_station\venv
base_station\venv\Scripts\python -m pip install -r base_station\requirements.txt
base_station\venv\Scripts\python -m base_station.ws_server.server

# 下载 OpenVINO 模型
# Optional model download via Git Bash: bash base_station/models/download_models.sh

# 启动 WebSocket 服务器
# python -m base_station.ws_server.server
```

Unix-like shell alternative:

```bash
cd base_station
python -m ws_server.server
```

### Start Agent Brain

Windows PowerShell/CMD, run from the repository root:

```powershell
python -m venv agent\venv
agent\venv\Scripts\python -m pip install -r agent\requirements.txt

# 初始化数据库
sqlite3 agent\data\xiao_an.db ".read agent\data\schema.sql"

# 启动大脑
agent\venv\Scripts\python -m agent.core.brain
```

### Start Mock Robot

```bash
python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765
```

### Send A Robot Command

```bash
python tools/send_robot_command.py expression caring
python tools/send_robot_command.py motion move_out_of_dock
python tools/send_robot_command.py tts "你已經工作很久了，休息一下吧。"
```

### Run Visual Active-Care Simulation

Neutral case should not trigger care:

```bash
python -m base_station.monitor.emotion_runtime --source fake_camera --model-backend mock --enable-vlm-gate --vlm-backend qwen_vl --pattern neutral --count 3 --fresh-db --verbose
```

Tired case should trigger care once, then cooldown:

```bash
python -m base_station.monitor.emotion_runtime --source fake_camera --model-backend mock --enable-vlm-gate --vlm-backend qwen_vl --pattern tired --count 3 --fresh-db --verbose
```

## Development Direction

The current direction should be:

1. Finish the **minimum hardware loop** first: ESP32 connects to `/control`, DK-2500 sends expression/motion commands, and ESP32 returns `device.status`, `motion.completed`, or `error.report`.
2. Validate the physical hardware in this order: TFT expression screen, OV2640 camera capture, DRV8833 + N20 motor movement, limit switch, speaker amp, INMP441 mic.
3. Add `/video` only after `/control` is stable: start with low-rate OV2640 JPEG frames, then feed DK-2500 OpenCV/OpenVINO perception.
4. Keep `/audio`, real ASR, and TTS playback as the second integration layer. INMP441 voice activity and MAX98357A playback should stay isolated until they are reliable.
5. Replace mock perception with real OpenVINO/OpenFace perception after the live control loop is observable and safe.
6. Review the unmerged remote perception/memory branches and merge them in a planned integration pass if their APIs match the current `main`.
7. Prepare the Intel Cup demo around one repeatable story: fatigue/perception trigger -> Agent decision -> caring expression -> short safe movement -> robot feedback.

## Protocol

The robot and base station communicate over WebSocket. See [docs/protocol.md](docs/protocol.md).

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

The intended privacy model is:

- Raw camera frames and microphone audio stay on the local robot/base-station system.
- Intel DK-2500 performs local perception and converts raw data into structured labels or summaries.
- Cloud LLM/OpenClaw should receive text summaries, state labels, and user-approved context, not raw audio/video.
- Local SQLite stores emotion history and interaction metadata.

## Team Roles

| Member | Role | Main Responsibility |
| --- | --- | --- |
| 張子尧 | App & Integration | Agent/runtime, skills, frontend, integration, docs |
| 鄭斯悅 / 鄭斯銳 | AI & Deployment | OpenVINO, ASR/VAD/TTS, model deployment, DK2500 |
| 施宇灏 | Hardware & Firmware | ESP32-S3 firmware, wiring, motors, shell, Dock |

## Files That Should Not Be Committed

- Real logs.
- SQLite databases.
- Local `.env` files and API keys.
- Virtual environments.
- `node_modules`.
- Downloaded model files.
- User private profile data.

Use `.env.example`, `base_station/config.example.yaml`, and `agent/data/schema.sql` as templates.

## License

MIT License. See [LICENSE](LICENSE).
