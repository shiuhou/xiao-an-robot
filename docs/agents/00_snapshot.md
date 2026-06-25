# 项目快照 — 2026-06-22

> 联调前 handoff。当前快照：`docs/project_status_2026-06-22.md`；旧版见 `docs/archive/`。

## 当前目标

**端到端闭环（优先于功能齐全）：**

1. ESP32 `/control`：hello + heartbeat + 自动重连
2. 基站下发 expression / motion / audio → 机器人执行 + `command.ack`
3. OV2640 → `/video` → 基站 `runtime/latest.jpg` → OpenVINO 情绪
4. （可选）mock ASR → OpenClaw → 主动关怀 Demo

## 进度总表

| 模块 | 状态 | 说明 |
|------|------|------|
| 协议 `docs/protocol.md` v0.1 | 🟡 | 草案；mergetesting 扩展了 `command.ack`, `video.frame_meta` |
| 基站 WS 四通道 | ✅ | `base_station/ws_server/server.py` |
| Agent → 机器人转发 | ✅ | `/agent` + `tools/send_robot_command.py` |
| 主固件机器人本体调试 | ✅ | `robot/firmware/src/main.cpp`；不作为 DK-2500 联调默认入口 |
| 主固件 `/video` `/audio` | ⬜ | `cam_stream`/`mic_stream` 在 main 里仍是 TODO |
| **mergetesting 联调固件** | ✅ 编译 | `robot/mergetesting/`，分 env 烧录 |
| 电机 DRV8833 | ✅ | isolated + mergetesting |
| 相机 OV2640 | ✅ | isolated；mergetesting 1fps WS |
| 128×160 TFT | ✅ | `display.cpp` |
| 2.4" face240 九表情 | ✅ | `robot_face_9expr_merged_optimized.cpp` / mergetesting |
| INMP441 麦克风 | 🟡 | RMS 测试 ✅；WS PCM 在 mergetesting |
| MAX98357A 喇叭 | 🟡 | 音调测试 ✅；mergetesting 本地音效 |
| 舵机 | ⬜ | `servo_ctrl` 全 stub |
| OpenVINO 真实 NPU 联调 | 🟡 | 单测/mock 多，硬件帧待接 |
| OpenClaw 完整 tools | 🟡 | MVP 路径有测试 |
| Frontend | ⬜ | 早期占位 |

## 近期重要变更（Agent 必知）

| 变更 | 路径 | 影响 |
|------|------|------|
| 仓库整理 2026-06-23 | `archive/`, `experiments/`, env 收斂 | 31→22 env；`tfttest`/`face240_espi`/8×tftprobe 移除 |
| 边界说明 | `robot/firmware/MIGRATION_FROM_MERGETESTING.md` | firmware 验证单项功能，mergetesting 做 DK-2500 联调 |
| 联调工程 | `robot/mergetesting/` | DK-2500 联调烧这个，不跑 firmware 的集成 env |
| WS 三通道客户端 | `mergetesting/src/ws_client.cpp` | control + video + audio |
| 基站收视频存盘 | `base_station/ws_server/server.py` | `runtime/latest.jpg` |
| `send_robot_command local` | `tools/send_robot_command.py` | 测 `audio.play_local` |
| face240 merged env | `face240_9expr_merged` in platformio.ini | 2.4 寸屏 bring-up |

## 硬件阻塞

- **整合线束**：TFT 默认 GPIO14/21/42/43/44/48，可与 OV2640 同接；旧 GPIO9–12 线束仅用 `face240_legacy`
- **限位开关**：`PIN_LIMIT_* = -1`，dock 逻辑未实机验证
- **WiFi 凭证**：`config.h` / `main.cpp` 占位，部署前必改

## 明日联调 env 速查

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only -t upload   # Phase 1-2
pio run -e mergetesting_cam_only -t upload       # Phase 3 传画
python -m base_station.ws_server.server          # 基站
```

## 谁改什么（减少 Agent 冲突）

| 目录 | 负责人（方案） | Agent 注意 |
|------|----------------|------------|
| `robot/firmware` | 施宇灏 | 小机器人单项功能调试；勿把联调 loop 塞进 `main.cpp` |
| `robot/mergetesting` | 联调专用 | 可激进；从 firmware 取用已验证模块，不回迁成 firmware 联调入口 |
| `base_station` | 郑斯悦+张子尧 | 改 protocol 要同步 `shared/` |
| `agent` | 张子尧 | Gateway/Brain 与 WS 耦合 |
| `docs/protocol.md` | 三人 PR | 破坏性变更升 major |
