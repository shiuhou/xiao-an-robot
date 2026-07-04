# 项目快照 — 2026-06-26 split env 全部 H

> 宽范围硬件/联调 baseline 仍是 `docs/status/2026-06-22.md`；OTA bootstrap 增量见 `docs/status/2026-06-25.md`；mergetesting split env 实机证据见 `docs/status/2026-06-26.md`。旧版见 `docs/archive/`。

## 当前目标

**端到端闭环（优先于功能齐全）：**

1. ESP32 `/control`：hello + heartbeat + capped 自动重连，重连后重发 `device.hello` — **split env H ✅**
2. 基站下发 expression / motion / local audio → 机器人执行 + `command.ack`；motion 同步 `action_id` 并回 `motion.completed` — **split env H ✅**
3. OV2640 → `/video` → 基站 `runtime/latest.jpg` → OpenVINO 情绪 — **传画 H ✅；OpenVINO 真实帧待接**
4. base-station mic / mock text → ASR/context → OpenClaw Gateway → 主动关怀 Demo — **mock transcript + real OpenClaw route P，real mic/robot H 待补**

## 进度总表

| 模块 | 状态 | 说明 |
|------|------|------|
| 协议 `docs/protocol/protocol.md` v0.1 | 🟡 | 草案；mergetesting 扩展了 `command.ack`, `video.frame_meta` |
| 基站 WS 四通道 | ✅ | `base_station/ws_server/server.py` |
| Agent → 机器人转发 | ✅ | `/agent` + `tools/send_robot_command.py` |
| 主固件机器人本体调试 | ✅ | `robot/firmware/src/main.cpp`；不作为 DK-2500 联调默认入口 |
| 主固件 `/video` `/audio` | ⬜ | DK-2500 联调放在 `robot/mergetesting`；robot-body 主固件不新增联调入口 |
| **mergetesting split env 联调** | ✅ H | 2026-06-26 全部 split env 实机通过；详见 `08_priority_queue_results.json` |
| **mergetesting 合并固件** | ✅ H | `mergetesting_full_face240` full env 通过 face240/speaker/camera/mic/motor H，2026-06-27 |
| **OpenClaw Step 33 care-demo 实机 preflight** | ✅ H / Demo 1 mock-transcript P | `mergetesting_care_demo_face240` 通过 `/control` caring、短移、`audio.play_tts` mock、`care_01`；motor 校准为 speed=0.56 约 1s 走 10cm；2026-07-03 OpenClaw Gateway `:18789` 已运行，Demo 1 mock transcript 经真实 `xiaoan-runtime` 返回 `xiaoan.robot.care` |
| 电机 DRV8833 | ✅ H | isolated + mergetesting；LEDC 通道 4-7 修复后方向正确 |
| 相机 OV2640 | ✅ H | mergetesting WS `/video` QVGA JPEG |
| 128×160 TFT | ✅ | `display.cpp` |
| 2.4" face240 九表情 | ✅ H | `mergetesting_face240_only` 实机 expression 通过；2026-06-30 开机默认直接渲染 `face=1` happy |
| INMP441 麦克风 | ✅ H / 固定窗口 ASR 前端 | RMS 测试 + mergetesting WS PCM `/audio`; current ASR demo path uses `mergetesting_mic_only_shift18_asr` plus base-station `--trim-speech` before SenseVoice |
| MAX98357A 喇叭 | ✅ H | 音调测试 + mergetesting lazy-I2S `/control` 本地音效 |
| OTA bootstrap | ✅ H | `ota_bootstrap` USB 首刷 + `ota_bootstrap_wifi` 无线刷新 bootstrap |
| 舵机 | ⬜ | `servo_ctrl` 全 stub |
| OpenVINO 真实 NPU 联调 | 🟡 | 单测/mock 多，硬件帧待接 |
| OpenClaw 完整 tools | 🟡 | OpenClaw `xiaoan-runtime` 负责工具选择；本地 tools 保留兼容测试 |
| Assistant capture demo | P | DK-2500/base mic 或 mock text -> ASR transcript -> `assistant_capture_context.v1` -> OpenClaw-owned note/idea/reminder/task/meeting capture result -> dashboard + optional robot expression/local-sound/TTS feedback；本地 SQLite compatibility tools 不作为产品成功证据 |
| Frontend | ⬜ | 早期占位 |
| Dock dashboard | P | `base_station/dashboard` 提供 1024x600 kiosk UI；`/api/dashboard/state` 返回 health + pipeline + 最近 3 条 triggers；无真实 trigger store 时读取 mock |

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
| Audio shared I2S half-duplex diagnostic 2026-06-29 | `robot/mergetesting/src/audio_shared_i2s_diag_main.cpp`, `robot/mergetesting/platformio.ini`, `tests/unit/test_mergetesting_layering.py` | `mergetesting_audio_shared_i2s_diag`：BCLK=39、WS=40、Mic SD=41、Speaker DIN=47；只跑半双工 LISTEN/SPEAK，不跑 Camera/TFT/Motor/WiFi/WebSocket；旧版 I2S0-TX 写满 PCM 但低频杂音；改为 mic RX=I2S0、speaker TX=I2S1 后早前 COM19/native-USB 听到完整句子；COM22 日志走 UART0 Serial0 RX=44 TX=43，已确认 app boot、1 kHz probe tone 写入 `bytes_written=18688`、phrase 写入 `bytes_written=97520`、`playback_done ok`、无 WDT/reset。若仍无声，firmware 执行不再是第一嫌疑，转查/替换 MAX98357A、喇叭输出端、SD/GAIN、5V 供电。 |
| **仓库整理 2026-06-27** | `docs/agents/10_repo_map.md`, `.gitignore`, `docs/archive/` | 删 `.pio`/clangd cache；归档 OpenFace handoff；跟踪 `.agents/skills/`；刷新 file_inventory |
| **OpenClaw 联调分析 2026-06-27** | `docs/agents/11_openclaw_robot_integration.md` | fusion 分支 care demo 与 mergetesting `/control` 协议一致；实机替换 mock_robot 即可 |
| **文档结构整理 2026-06-28** | `README.md`, `docs/README.md`, `docs/current_status.md`, `docs/status/`, `docs/setup/`, `docs/testing/smoke/` | Root README 变为入口页；当前状态与历史快照分离；新 Agent 先读 `docs/current_status.md` |
| **机器人目录入口 2026-06-29** | `robot/README.md`, `robot/firmware/README.md`, `robot/mergetesting/MAIN_DEMO.md` | 明确 `robot/mergetesting` 是 DK-2500 主线，`robot/firmware` 是 bring-up lab；主 demo 命令集中到 `MAIN_DEMO.md` |
| **运行目录入口 2026-06-29** | `base_station/README.md`, `agent/README.md`, `tools/README.md`, `scripts/README.md` | Base station、local Agent、tools、scripts 均有入口说明；先标注用途和 legacy/diagnostic 边界，不移动文件 |
| **Git hygiene 盘点 2026-06-29** | `.gitignore`, `docs/runbooks/git_hygiene.md` | OpenFace IR 明确为 Git LFS 例外；`base_station/config.yaml` 已确认可公开并保留 tracked |
| **代码结构 inventory 2026-06-29** | `docs/agents/13_code_structure_inventory.md`, `robot/firmware/src/archive/`, `docs/setup/m600_deployment.md` | 已建立结构整理批次清单；legacy `integrated_main.cpp` 移出 active src 根但保留 legacy env 编译；M600 部署笔记移入 `docs/setup/` |
| **OpenFace runtime 标记 2026-06-29** | `base_station/perception/openface_ov_runtime/README.md`, `docs/agents/04_base_station_agent_registry.md` | `openface_ov_runtime/` 是 bundled vendored runtime，`ov_perceive.py` 依赖 runtime root / `Pytorch_Retinaface` / `STAR` 的 `sys.path` 插入；普通仓库整理不要移动 |
| **Dock dashboard 触发链路栏 2026-06-29** | `base_station/dashboard/`, `docs/runbooks/base_station_dashboard.md`, `tests/unit/test_dashboard_server.py` | `/dashboard` 右侧显示 Base/Robot/Agent/Camera/Audio、`Robot -> Base -> Agent -> Action`、最近 3 条触发；1024x600 headless 检查无 overflow |
| **Wiring stale-reference sweep 2026-06-30** | `hardware/wiring/esp32_pinout.md`, `docs/current_status.md`, `docs/agents/13_code_structure_inventory.md` | 修正 wiring canonical page：当前 shared-clock candidate 是 INMP441 39/40/41 + MAX98357A 39/40/47；GPIO35/36/37 标为当前 Octal PSRAM MAX98357A 避免项；inventory 下一批次改为 C6 stale wiring/status sweep |
| **Dock dashboard glance UI 2026-06-30** | `base_station/dashboard/static/dashboard.*`, `docs/runbooks/base_station_dashboard.md`, `tests/unit/test_dashboard_server.py` | `/dashboard` 默认改为远距离可读 glance screen：大号当前状态、下一件事、系统健康 chips、最新 1 条触发、紧凑链路；1024x600 Chromium screenshot 已检查 |
| **Tools physical grouping 2026-06-30** | `tools/ops/`, `tools/probes/`, `tools/evaluation/`, `tools/setup/`, `tools/maintenance/`, `tools/legacy/` | 工具实作已按职责实体现分组；根层 `tools/*.py` 保留兼容 wrapper，旧命令和 `tools.*` imports 继续可用 |
| **Scripts physical grouping 2026-06-30** | `scripts/setup/`, `scripts/start/`, `scripts/debug/` | 启动、setup、debug 脚本已按职责实体现分组；根层 `scripts/*.sh` / `scripts/*.py` 保留 wrapper，旧命令继续可用 |
| **Code naming cleanup inventory 2026-06-30** | `docs/agents/14_naming_inventory.md`, `tools/legacy/manual_*_smoke.py` | 命名整改控制表已建立；legacy manual smoke 实作不再使用 `test_*` 文件名，根层 `tools/test_*.py` 保留兼容 wrapper |
| **Firmware entrypoint naming 2026-06-30** | `robot/firmware/src/*_main.cpp`, `robot/firmware/platformio.ini`, `docs/agents/02_firmware_registry.md` | active bring-up entrypoint 文件名已从 `_test.cpp` 改为用途明确的 `_main.cpp`/`_smoke_main.cpp`/`_check_main.cpp`；PlatformIO env 名保持不变 |
| **Fixed-window ASR module naming 2026-06-30** | `base_station/monitor/fixed_window_asr_demo.py`, `base_station/monitor/continuous_asr_demo.py`, `tests/unit/test_fixed_window_asr_demo.py` | ASR demo 主 module 改为 fixed-window 命名；旧 `continuous_asr_demo.py` 保留 compatibility wrapper |
| **证据包整理 2026-07-01** | `report_evidence/` | 按“时间戳 / 环境 / 输入 / 处理 / 输出 / 结论 / 代码路径”格式整理 `/control`、`/video`、`/audio`、OpenClaw、主动关怀、私人助理、DK-2500 角色和问题修复证据；只使用现有 runtime/docs 证据，未新增实机运行 |
| **Base-station mic 主线切换 2026-07-02** | `docs/current_status.md`, `docs/runbooks/main_demo_care_loop.md`, `base_station/README.md`, `base_station/monitor/README.md`, `docs/agents/04_base_station_agent_registry.md`, `docs/agents/05_test_matrix.md` | 9 天 demo 正式输入改为 DK-2500/base-station mic；robot `/audio` 保留为 fallback/diagnostics；目标闭环为 base mic -> ASR -> context -> OpenClaw/Agent -> `/control` -> ack/completed |
| **Demo 1 USB mic 到 Agent screen 2026-07-02** | `tools/demo/demo1_usb_mic_to_agent_screen.py`, `docs/runbooks/demo1_usb_mic_to_agent_screen.md`, `tests/unit/test_demo1_usb_mic_to_agent_screen.py` | 最小闭环工具：DK-2500 USB mic fixed-window WAV -> 复用 `asr_runtime` -> `runtime/demo1_transcript.json` -> `http://localhost:8766`；mock fallback 明确标记 `source=mock` |
| **Demo 1 local-rule 临时动作计划 2026-07-03** | `tools/demo/demo1_usb_mic_to_agent_screen.py`, `runtime/demo1_openclaw_context.json`, `runtime/demo1_action_plan.json` | 早期 `--route-agent` 本地规则 fallback 曾用于快速验证 `/agent` 转发；现已降级为 legacy diagnostic，不是主 demo 路径。主路径见下方“Demo 1 真实 OpenClaw Gateway 路由” |
| **Demo 1 OpenClaw context/action plan 收口 2026-07-03** | `tools/demo/demo1_usb_mic_to_agent_screen.py`, `docs/runbooks/demo1_usb_mic_to_agent_screen.md`, `tests/unit/test_demo1_usb_mic_to_agent_screen.py` | 固定 `demo1.openclaw_context.v1` 与 `demo1.action_plan.v1` JSON；context 顶层包含 transcript/source/timestamp/robot_state/vision_context/last_action/demo_intent/allowed_actions；主 OpenClaw 路径只记录 `route=openclaw_gateway` 空 actions，真实决策在 `demo1_openclaw_result.json`；发送给 OpenClaw 的工具 manifest 已过滤到 Demo 1 白名单；reply-text-only、unsupported tool/expression、local-rule route 均不能作为主 demo 成功证据 |
| **Demo 1 表情协议一致性实机 H 2026-07-03** | `tools/demo/demo1_usb_mic_to_agent_screen.py`, `base_station/ws_server/protocol.py`, `robot/mergetesting/src/protocol.h`, `robot/mergetesting/src/face240_display.cpp` | Demo 1 `allowed_actions` 表情收敛到 `/agent` Python enum 与 `robot/mergetesting` 固件共同支持集合；expression diagnostic 验证 `happy/caring/surprised/thinking` 均生成 `display.expression`、`agent.ack ok`，USB 串口确认固件收到 `/control` 且回 `command.ack display.expression -> ok`；`angry/calm/neutral` 不在 Demo 1 表情白名单内，不能作为主 demo 成功 |
| **Demo 1 真实 OpenClaw Gateway 路由 2026-07-03** | `tools/demo/demo1_usb_mic_to_agent_screen.py`, `tools/demo/run_demo1_mic_to_robot.sh`, `runtime/demo1_openclaw_result.json`, `docs/status/2026-07-03.md` | 主脚本默认从 `--route-agent` 本地规则改为 `--route-openclaw`：ASR/mock transcript -> `demo1.openclaw_context.v1` -> `GatewayOpenClawAdapter` -> `ws://127.0.0.1:18789` / `xiaoan-runtime` -> strict `validate_openclaw_decision()` -> `ActionExecutor` -> `/agent`。Mock 输入“小安，我有点累”已返回 `xiaoan.robot.care` 并执行 `display.expression`/`motion.execute`/`audio.play_local care_01`；robot log 已见 expression/motion command ack 与 `motion.completed`，但 local audio 返回 `speaker not ready`；真实 mic ASR 目标短句仍需重测 |
| **Assistant capture demo 2026-07-03** | `tools/demo/demo_assistant_capture.py`, `base_station/dashboard/`, `docs/runbooks/demo_assistant_capture.md`, `tests/unit/test_demo_assistant_capture.py`, `tests/unit/test_dashboard_server.py` | 新增 casual voice capture demo：base-station mic/mock text -> ASR transcript -> `assistant_capture_context.v1` -> OpenClaw Gateway `xiaoan-runtime` owned capture result -> dashboard and optional robot expression/local sound/TTS feedback。验证拒绝 reply-text-only 和本地 SQLite `note/reminder/task` compatibility tools 作为产品成功；OpenClaw offline smoke 退出 1 并写 `failed`，不假保存。目标相关 80 tests PASS；全量 discover 当前 1043 tests 中 4 failures/10 errors，集中在既有 emotion care 测试仍期望 `audio.play_tts` 或 FakeGateway 缺 `send_local_audio`，非本次改动范围。链路改进记录已写入 runbook。 |
| **Visual-chain camera-free preflight 2026-07-03** | `tools/prepare_visual_chain_preflight.py`, `tools/ops/prepare_visual_chain_preflight.py`, `docs/runbooks/demo1_visual_chain_handoff.md`, `tests/unit/test_prepare_visual_chain_preflight.py`, `base_station/requirements-vlm.txt` | 新增无需机器人 camera frame 的视觉准备检查：静态图片 decode、mock `emotion_runtime`、OpenFace OV runtime/model/import readiness + Git LFS pointer detection、Qwen OpenVINO model/import readiness、可选 OpenClaw socket 和 real-model runtime。当前本机已安装视觉依赖并补 `scikit-image`/`pandas` 到 requirements；`git lfs pull --include="base_station/models/openface_ov/**"` 后 OpenFace readiness 与 `--run-openface` 均 PASS；Qwen 下载仍未完成，缺 `openvino_language_model.bin`、`openvino_text_embeddings_model.bin`、`openvino_vision_embeddings_merger_model.bin`。 |
| **Demo tool guardrails 2026-07-03** | `tools/demo/demo_assistant_capture.py`, `tools/ops/prepare_visual_chain_preflight.py`, `tests/unit/test_demo_assistant_capture.py`, `tests/unit/test_prepare_visual_chain_preflight.py` | 低风险 Python-only hardening：assistant capture 空 `--mock-text` 直接失败，避免假 `ignored` 成功；visual preflight timeout 输出保持 JSON-safe，坏 Qwen manifest 变成 readiness failure，relative OpenFace/Qwen paths 从 repo root 解析。验证：`.venv/bin/python -m unittest tests.unit.test_demo_assistant_capture tests.unit.test_dashboard_server tests.unit.test_prepare_visual_chain_preflight` PASS 27 tests；未触碰 firmware/mergetesting/协议。 |
| **Integration Console 2026-07-04** | `base_station/integration_console/`, `base_station/ws_server/server.py`, `docs/runbooks/integration_console.md` | 新增 DK-2500 硬件联调控制台 `/console`：聚合 `runtime/ws_state.json`、latest image/audio、OpenClaw 状态、场景脚本、白名单工具、JSONL 日志和导出；`ws_server` 最小侵入式写 atomic `runtime/ws_state.json`；软件 targeted tests PASS，真实硬件链路待现场验证。 |

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
| `docs/protocol/protocol.md` | 三人 PR | 破坏性变更升 major |

## 2026-07-04 Addendum

- Streamed spoken TTS: this PC as base station streamed arbitrary `audio.play_tts`
  text to the COM23 ESP32 over `/agent -> /control`. Low-volume
  `XIAOAN_TTS_TARGET_PEAK=800` checks reached `audio.playback_done ok` for
  `你好`, `你好，我是小安。`, and an arbitrary OpenClaw sentence.

## 2026-07-04 OpenClaw Preflight Addendum

- Added `docs/runbooks/openclaw_preflight_acceptance.md` as the current
  action-by-action checklist before connecting the real OpenClaw decision loop.
  It uses the spoken TTS baseline of base station `XIAOAN_TTS_TARGET_PEAK=800`,
  `XIAOAN_TTS_VOICE='Microsoft Hanhan Desktop'`, and ESP stream gain `32`.
- P0 preflight passed on COM23 with `python tools\run_openclaw_preflight_p0.py
  --device-id xiaoan_robot_01`: robot online, streamed TTS intro/arbitrary
  sentence/fallback phrase, local `wake_01`, thinking/speaking face, and
  stop-only motion command all returned robot-side event evidence. SAPI voice
  quality is acceptable as a temporary demo baseline but not final product TTS.
