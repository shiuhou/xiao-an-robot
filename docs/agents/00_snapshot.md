# 项目快照 — 2026-06-26 split env 全部 H

> 宽范围硬件/联调 baseline 仍是 `docs/status/2026-06-22.md`；OTA bootstrap 增量见 `docs/status/2026-06-25.md`；mergetesting split env 实机证据见 `docs/status/2026-06-26.md`。旧版见 `docs/archive/`。

## 当前目标

**端到端闭环（优先于功能齐全）：**

1. ESP32 `/control`：hello + heartbeat + capped 自动重连，重连后重发 `device.hello` — **split env H ✅**
2. 基站下发 expression / motion / local audio → 机器人执行 + `command.ack`；motion 同步 `action_id` 并回 `motion.completed` — **split env H ✅**
3. OV2640 → `/video` → 基站 `runtime/latest.jpg` → OpenVINO 情绪 — **传画 H ✅；OpenVINO 真实帧待接**
4. （可选）mock ASR → OpenClaw → 主动关怀 Demo — **未做**

## 进度总表

| 模块 | 状态 | 说明 |
|------|------|------|
| 协议 `docs/protocol.md` v0.1 | 🟡 | 草案；mergetesting 扩展了 `command.ack`, `video.frame_meta` |
| 基站 WS 四通道 | ✅ | `base_station/ws_server/server.py` |
| Agent → 机器人转发 | ✅ | `/agent` + `tools/send_robot_command.py` |
| 主固件机器人本体调试 | ✅ | `robot/firmware/src/main.cpp`；不作为 DK-2500 联调默认入口 |
| 主固件 `/video` `/audio` | ⬜ | DK-2500 联调放在 `robot/mergetesting`；robot-body 主固件不新增联调入口 |
| **mergetesting split env 联调** | ✅ H | 2026-06-26 全部 split env 实机通过；详见 `08_priority_queue_results.json` |
| **mergetesting 合并固件** | ✅ H | `mergetesting_full_face240` full env 通过 face240/speaker/camera/mic/motor H，2026-06-27 |
| **OpenClaw Step 33 care-demo 实机 preflight** | ✅ H / demo 待跑 | `mergetesting_care_demo_face240` 通过 `/control` caring、短移、`audio.play_tts` mock、`care_01`；motor 校准为 speed=0.56 约 1s 走 10cm；Gateway `:18789` 未运行 |
| 电机 DRV8833 | ✅ H | isolated + mergetesting；LEDC 通道 4-7 修复后方向正确 |
| 相机 OV2640 | ✅ H | mergetesting WS `/video` QVGA JPEG |
| 128×160 TFT | ✅ | `display.cpp` |
| 2.4" face240 九表情 | ✅ H | `mergetesting_face240_only` 实机 expression 通过 |
| INMP441 麦克风 | ✅ H / 诊断增强 | RMS 测试 + mergetesting WS PCM `/audio`; base station now exports raw PCM to WAV and records latest-window RMS/peak/DC/clipping stats before ASR tuning |
| MAX98357A 喇叭 | ✅ H | 音调测试 + mergetesting lazy-I2S `/control` 本地音效 |
| OTA bootstrap | ✅ H | `ota_bootstrap` USB 首刷 + `ota_bootstrap_wifi` 无线刷新 bootstrap |
| 舵机 | ⬜ | `servo_ctrl` 全 stub |
| OpenVINO 真实 NPU 联调 | 🟡 | 单测/mock 多，硬件帧待接 |
| OpenClaw 完整 tools | 🟡 | OpenClaw `xiaoan-runtime` 负责工具选择；本地 tools 保留兼容测试 |
| Frontend | ⬜ | 早期占位 |

## Step 30.1 职责边界

- OpenClaw `xiaoan-runtime` 负责用户画像、长期记忆、定时提醒、任务、晨报/日报、自然语言回复和工具选择。
- `xiao-an-robot` 负责机器人身体、感知链路、本地情绪阈值、安全策略、ESP32 通信、机器人动作执行和本地事件日志。
- SQLite 是 Local Event Store，不是用户长期记忆主源。
- 本地 reminders/tasks/notes/summaries/work_activity 只作为 legacy compatibility。
- screen monitoring 已退出 MVP。

## 近期重要变更（Agent 必知）

| 变更 | 路径 | 影响 |
|------|------|------|
| 仓库整理 2026-06-23 | `archive/`, `experiments/`, env 收斂 | 31→22 env；`tfttest`/`face240_espi`/8×tftprobe 移除 |
| 边界说明 | `robot/firmware/MIGRATION_FROM_MERGETESTING.md` | firmware 验证单项功能，mergetesting 做 DK-2500 联调 |
| 联调工程 | `robot/mergetesting/` | DK-2500 联调烧这个，不跑 firmware 的集成 env |
| WS 三通道客户端 | `mergetesting/src/ws_client.cpp` | control + video + audio；媒体通道由 feature macro 守卫 |
| 基站收视频存盘 | `base_station/ws_server/server.py` | `runtime/latest.jpg` |
| `send_robot_command local` | `tools/send_robot_command.py` | 测 `audio.play_local`；motion 支持 `--bench`、`--speed`、`--distance-cm`、`--duration-ms`、`--timeout-ms` |
| face240 merged env | `face240_9expr_merged` in platformio.ini | 2.4 寸屏 bring-up |
| OTA bootstrap 2026-06-25 | `docs/status/2026-06-25.md` | USB 首刷后可无线刷新 bootstrap；不是通用上传任意 env |
| 分层架构 spec 2026-06-25 | `docs/superpowers/specs/2026-06-25-layered-firmware-architecture-design.md` | 保留 bring-up env，逐步抽 services/hal/transport/protocol |
| mergetesting 分层 Phase 1 2026-06-26 | `robot/mergetesting/src/app/`, `robot/mergetesting/src/services/` | `main.cpp` thin entrypoint；non-blocking motion + command router |
| split env 实机 H 2026-06-26 | `docs/status/2026-06-26.md`, `08_priority_queue_results.json` | T07–T16 全部 PASS_H |
| full env 实机 H 2026-06-27 | `mergetesting_full_face240`, `08_priority_queue_results.json` | T17 PASS_H；三通道 + full-speed 5s motor |
| care-demo face240 env 2026-06-27 | `mergetesting_care_demo_face240`, `08_priority_queue_results.json` | Step 33 实机前置固件；face240/motor/speaker/control only，禁用 camera/mic |
| 电机 LEDC 修复 2026-06-26/27 | `robot/mergetesting/src/motor_ctrl.cpp`, `platformio.ini` | split motor 保留 4–7；full 避开 camera LEDC；USB full upload 用 460800 |
| 喇叭 lazy-I2S 2026-06-26 | `robot/mergetesting/src/speaker.cpp` | 本地音效仍是可靠发声路径；显式开启 PCM spoken TTS 时仍会在 PCM-to-I2S 播放阶段 WDT |
| Speaker OTA/TTS guard 2026-06-28 | `base_station/ws_server/server.py`, `robot/mergetesting/src/speaker.cpp`, `robot/mergetesting/platformio.ini` | ESP32 OTA IP `192.168.137.147`，host `192.168.137.1`；默认 `audio.play_tts` 为 metadata-only/mock-tone 安全路径，PCM 串流需 `XIAOAN_CONTROL_TTS_STREAM=1` 诊断 |
| Speaker PCM playback diagnostics 2026-06-29 | `robot/mergetesting/src/speaker.cpp`, `robot/mergetesting/src/embedded_tts_phrase.h`, `tests/unit/test_mergetesting_layering.py` | COM19 证实原 GPIO35/36/37 speaker 路径在 embedded PCM first write 后 `TG1WDT_SYS_RST`；GPIO39/40/41 speaker-only A/B 已通过串口本地音效、corrected-wiring embedded PCM、以及外部 5V/no-USB WebSocket `audio.play_tts`，用户听到完整 `I can speak now.`；`audio.playback_done status=ok bytes_written=97520 duration_ms=1557`。Repo gain 已调到 16，但未在课堂期间 OTA/发声复测。 |
| **仓库整理 2026-06-27** | `docs/agents/10_repo_map.md`, `.gitignore`, `docs/archive/` | 删 `.pio`/clangd cache；归档 OpenFace handoff；跟踪 `.agents/skills/`；刷新 file_inventory |
| **OpenClaw 联调分析 2026-06-27** | `docs/agents/11_openclaw_robot_integration.md` | fusion 分支 care demo 与 mergetesting `/control` 协议一致；实机替换 mock_robot 即可 |
| **文档结构整理 2026-06-28** | `README.md`, `docs/README.md`, `docs/current_status.md`, `docs/status/`, `docs/setup/`, `docs/testing/smoke/` | Root README 变为入口页；当前状态与历史快照分离；新 Agent 先读 `docs/current_status.md` |
| **机器人目录入口 2026-06-29** | `robot/README.md`, `robot/firmware/README.md`, `robot/mergetesting/MAIN_DEMO.md` | 明确 `robot/mergetesting` 是 DK-2500 主线，`robot/firmware` 是 bring-up lab；主 demo 命令集中到 `MAIN_DEMO.md` |
| **运行目录入口 2026-06-29** | `base_station/README.md`, `agent/README.md`, `tools/README.md`, `scripts/README.md` | Base station、local Agent、tools、scripts 均有入口说明；先标注用途和 legacy/diagnostic 边界，不移动文件 |
| **Git hygiene 盘点 2026-06-29** | `.gitignore`, `docs/runbooks/git_hygiene.md` | OpenFace IR 明确为 Git LFS 例外；`base_station/config.yaml` 已确认可公开并保留 tracked |
| **代码结构 inventory 2026-06-29** | `docs/agents/13_code_structure_inventory.md`, `robot/firmware/src/archive/`, `docs/setup/m600_deployment.md` | 已建立结构整理批次清单；legacy `integrated_main.cpp` 移出 active src 根但保留 legacy env 编译；M600 部署笔记移入 `docs/setup/` |

## 硬件阻塞（剩余）

- **限位开关**：`PIN_LIMIT_* = -1`，dock 逻辑未实机验证
- **WiFi 凭证**：`config.local.h` 部署前必改（已本地配置，不入 Git）
- **合并固件稳定性**：split env 全 H 后仍需单独验证 `mergetesting` 合并烧录

## 下一步 env 速查

```powershell
cd robot\mergetesting
pio run -e mergetesting_care_demo_face240 -t upload --upload-port COMxx
python -m base_station.ws_server.server                 # 基站
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression caring
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion move_out_of_dock
python tools\send_robot_command.py --device-id xiaoan_robot_01 tts --text "测试"
```

Phase 4 闭环（video → OpenVINO → OpenClaw → 三命令）见 `06_integration_phases.md`。

## 谁改什么（减少 Agent 冲突）

| 目录 | 负责人（方案） | Agent 注意 |
|------|----------------|------------|
| `robot/firmware` | 施宇灏 | 小机器人单项功能调试；勿把联调 loop 塞进 `main.cpp` |
| `robot/mergetesting` | 联调专用 | 可激进；从 firmware 取用已验证模块，不回迁成 firmware 联调入口 |
| `base_station` | 郑斯悦+张子尧 | 改 protocol 要同步 `shared/` |
| `agent` | 张子尧 | Gateway/Brain 与 WS 耦合 |
| `docs/protocol.md` | 三人 PR | 破坏性变更升 major |
