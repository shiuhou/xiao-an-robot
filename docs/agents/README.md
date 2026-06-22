# AI Agent 项目上下文 — 入口

> **给所有 AI Agent 的第一份文档。** 开始任务前请先读本文 + 最新快照。
> 最后更新：2026-06-22

## 30 秒项目是什么

小安机器人：ESP32-S3 本体 + Intel DK-2500 基站 + OpenClaw Agent。
通信：**WebSocket**（`/control` JSON、`/video` JPEG、`/audio` PCM）。

```
摄像头/麦克风 → ESP32 → ws://基站:8765 → OpenVINO/ASR → OpenClaw → 表情/电机/语音 → ESP32
```

## 阅读顺序（按任务类型）

| 你要做什么 | 先读 |
|-----------|------|
| 任何任务 | 本文 + [00_snapshot](./00_snapshot.md) |
| 改 ESP32 固件 | [02_firmware_registry](./02_firmware_registry.md) + [03_mergetesting](./03_mergetesting_registry.md) |
| 改基站 / Agent | [04_base_station_agent](./04_base_station_agent_registry.md) |
| 跑测试 / CI | [05_test_matrix](./05_test_matrix.md) |
| 联调 / Demo | [06_integration_phases](./06_integration_phases.md) + `docs/protocol.md` |
| 更新文档 | [07_maintenance](./07_maintenance.md) |

## 文档层级（不要混用）

| 层级 | 路径 | 粒度 | 谁维护 |
|------|------|------|--------|
| **契约** | `docs/protocol.md`, `shared/protocol/*` | 消息格式 | 三人共识后改 |
| **快照** | `docs/project_status_YYYY-MM-DD.md`, `docs/agents/00_snapshot.md` | 当前进度/阻塞 | 每次联调前后 |
| **注册表** | `docs/agents/02_*` ~ `04_*` | **文件 + 关键函数** | 改代码时同步 |
| **源码** | `robot/firmware/src/*` 等 | 逐行真相 | Git |

**不要**在注册表里复制整文件源码；用「路径 + 函数 + 状态 + 最后验证命令」即可。

## 状态图例（全库统一）

| 标记 | 含义 |
|------|------|
| ✅ | 已实现且在目标 env 编译/测试通过 |
| 🟡 | 部分实现或仅 isolated env 可用 |
| ⬜ | stub / TODO |
| 🔴 | 已知阻塞（引脚冲突、未联调等） |
| 🧪 | 仅单元测试/mock，未接硬件 |

## 两条固件线（极易混淆）

| 路径 | 用途 | 传画面方式 |
|------|------|-----------|
| `robot/firmware` + `esp32-s3-devkitc-1` | 主固件 `/control` | `/video` **未接** main loop |
| `robot/mergetesting` | **明日 DK-2500 联调** | WebSocket `/video` 1fps JPEG |
| `motor_cam_wifi_manual` env | 单机硬件 demo | ESP32 AP + HTTP MJPEG `:81/stream` |

## 刷新注册表（可选）

```powershell
python tools/generate_agent_registry.py
```

会更新 `docs/agents/_generated/` 下的文件清单（不覆盖人工写的状态列）。

## 相关文件

- 人类可读总览：`docs/architecture.md`, `docs/hardware_setup.md`
- Agent 规则：`AGENTS.md`（仓库根）
- 联调对接表：`robot/mergetesting/CAPABILITIES.md`
