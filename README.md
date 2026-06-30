# Xiao An Robot

小安是一個基於 Intel DK-2500 / Core Ultra 基站與 ESP32-S3 機器人本體的桌面情感陪伴機器人。

這個 repo 負責機器人身體、本地感知、WebSocket 通信、安全動作執行與本地事件記錄。OpenClaw `xiaoan-runtime` 負責使用者理解、長期記憶、提醒、任務、自然語言回覆與工具選擇。

## Start Here

| 目的 | 先讀 |
| --- | --- |
| 看當前能跑什麼 | [docs/current_status.md](docs/current_status.md) |
| 找文檔入口 | [docs/README.md](docs/README.md) |
| Agent 接手任務 | [AGENTS.md](AGENTS.md) + [docs/agents/README.md](docs/agents/README.md) |
| 跑主 demo | [docs/runbooks/main_demo_care_loop.md](docs/runbooks/main_demo_care_loop.md) |
| 查歷史狀態 | [docs/status/](docs/status/) |
| 改 DK-2500 聯調 firmware | [robot/mergetesting/README.md](robot/mergetesting/README.md) + [docs/agents/03_mergetesting_registry.md](docs/agents/03_mergetesting_registry.md) |
| 改 robot-body bring-up firmware | [docs/agents/02_firmware_registry.md](docs/agents/02_firmware_registry.md) + `robot/firmware/platformio.ini` |
| 改 protocol | [docs/protocol/protocol.md](docs/protocol/protocol.md) + `shared/protocol/*` + firmware `protocol.h` |

## Main Demo Path

```text
OpenClaw / Agent
-> base_station WebSocket /agent and /control
-> robot/mergetesting
-> face expression + motion + local sound
```

Current main integration firmware lives in `robot/mergetesting`.

`robot/firmware` is the robot-body bring-up lab and reusable-module source. Do not add new DK-2500 `/control`, `/video`, or `/audio` integration entrypoints there.

## Quick Start

Start the base station:

```powershell
python -m base_station.ws_server.server
```

Build and flash the current full-demo robot firmware:

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240
pio run -e mergetesting_full_face240 -t upload --upload-port COM19
```

Run direct smoke commands:

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion left --bench --speed 0.56 --duration-ms 500 --timeout-ms 700
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

Run the Python test suite:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

See [docs/current_status.md](docs/current_status.md) for the latest verified baseline and caveats.

## Repository Map

```text
xiao-an-robot/
├── robot/
│   ├── mergetesting/       # DK-2500/base-station integration firmware
│   └── firmware/           # ESP32-S3 robot-body bring-up and reusable modules
├── base_station/           # WebSocket server, perception runtime, ASR/emotion loops
├── agent/                  # local brain/gateway/skills compatibility layer
├── shared/                 # protocol schema, constants, and examples
├── frontend/               # debug console, not required for the main hardware demo
├── hardware/               # BOM, wiring, DK-2500, shell, and dock notes
├── docs/                   # current status, runbooks, setup, protocol, archive
├── tests/                  # unit/integration tests and mock robot
├── tools/                  # local operation and probe scripts
└── scripts/                # startup/setup helper scripts
```

## Truth Sources

When documents disagree, use this order:

1. Live source and `platformio.ini`
2. [AGENTS.md](AGENTS.md)
3. [docs/current_status.md](docs/current_status.md)
4. Latest dated status in [docs/status/](docs/status/)
5. Agent registries in [docs/agents/](docs/agents/)
6. [docs/archive/](docs/archive/)

Important entry points:

| Topic | Source |
| --- | --- |
| Current demo baseline | [docs/current_status.md](docs/current_status.md) |
| Documentation map | [docs/README.md](docs/README.md) |
| Agent workflow | [docs/agents/README.md](docs/agents/README.md) |
| Firmware env roles | `robot/firmware/platformio.ini`, [docs/agents/02_firmware_registry.md](docs/agents/02_firmware_registry.md) |
| Mergetesting env roles | `robot/mergetesting/platformio.ini`, [docs/agents/03_mergetesting_registry.md](docs/agents/03_mergetesting_registry.md) |
| Test matrix | [docs/agents/05_test_matrix.md](docs/agents/05_test_matrix.md) |
| Message contract | [docs/protocol/protocol.md](docs/protocol/protocol.md), `shared/protocol/*` |
| Wiring assumptions | [hardware/wiring/esp32_pinout.md](hardware/wiring/esp32_pinout.md), [docs/hardware_setup.md](docs/hardware_setup.md) |
| OpenClaw boundary | [docs/openclaw/openclaw_ownership_boundary.md](docs/openclaw/openclaw_ownership_boundary.md) |

## Development Boundaries

| Change type | Work in |
| --- | --- |
| Single robot-body hardware bring-up | `robot/firmware` with a dedicated PlatformIO env |
| DK-2500/base-station integration | `robot/mergetesting` |
| Proven module reused by integration | validate in `robot/firmware`, then copy/sync minimal module into `robot/mergetesting` |
| Protocol changes | `docs/protocol/protocol.md`, `shared/protocol/*`, firmware `protocol.h` |
| Wiring/env command changes | `docs/hardware_setup.md`, `hardware/wiring/*`, `docs/agents/*` |

Validate firmware with specific envs, not broad `pio run`.

## Do Not Commit

- real logs
- SQLite databases
- local `.env` files and API keys
- real `config.local.h` or `config.local.yaml`
- virtual environments
- `node_modules`
- downloaded model files or large model binaries
- `.pio` / PlatformIO build output
- runtime audio/video/image captures
- user private profile data

Use `.env.example`, `base_station/config.example.yaml`, `robot/firmware/src/config.local.example.h`, `robot/mergetesting/src/config.local.example.h`, and `agent/data/schema.sql` as templates.

## License

MIT License. See [LICENSE](LICENSE).
