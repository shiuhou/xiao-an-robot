# AI Agent 项目上下文 — 入口

> **给所有 AI Agent 的第一份文档。** 开始任务前请先读本文 + 最新快照 + 开工协议。
> **Codex 为主力**：用户说 `按 xiao-an-session 开工` → 读 [01_session_protocol](./01_session_protocol.md)。
> 最后更新：2026-06-26

## 30 秒项目是什么

小安机器人：ESP32-S3 本体 + Intel DK-2500 基站 + OpenClaw Agent。
通信：**WebSocket**（`/control` JSON、`/video` JPEG、`/audio` PCM）。

```
摄像头/麦克风 → ESP32 → ws://基站:8765 → OpenVINO/ASR → OpenClaw → 表情/电机/语音 → ESP32
```

## 阅读顺序（按任务类型）

| 你要做什么 | 先读 |
|-----------|------|
| **Codex 开工 / 收工 / 多 Agent 对齐** | [01_session_protocol](./01_session_protocol.md) + Skill `xiao-an-session` |
| 任何任务 | 本文 + [00_snapshot](./00_snapshot.md) + [01_session_protocol](./01_session_protocol.md) §6 |
| 改 ESP32 固件 | [02_firmware_registry](./02_firmware_registry.md) + [03_mergetesting](./03_mergetesting_registry.md) |
| 改基站 / Agent | [04_base_station_agent](./04_base_station_agent_registry.md) |
| 跑测试 / CI | [05_test_matrix](./05_test_matrix.md) |
| 联调 / Demo | [06_integration_phases](./06_integration_phases.md) + `docs/protocol.md` |
| Agent loop 排队 | [08_priority_queue](./08_priority_queue.yaml) |
| 明天上机检查 | [09_hardware_bringup_checklist](./09_hardware_bringup_checklist.md) |
| 架构整理 / 分层重构 | `docs/superpowers/specs/2026-06-25-layered-firmware-architecture-design.md` |
| 更新文档 | [07_maintenance](./07_maintenance.md) |
| 整合 Agent / 整库索引 | [10_repo_map](./10_repo_map.md) |
| OpenClaw ↔ 实机联调 | [11_openclaw_robot_integration](./11_openclaw_robot_integration.md) |
| **实机 emotion care Codex prompt** | [12_codex_prompt_real_emotion_care_demo](./12_codex_prompt_real_emotion_care_demo.md) |

## 文档层级（不要混用）

| 层级 | 路径 | 粒度 | 谁维护 |
|------|------|------|--------|
| **契约** | `docs/protocol.md`, `shared/protocol/*` | 消息格式 | 三人共识后改 |
| **快照** | `docs/project_status_YYYY-MM-DD.md`, `docs/agents/00_snapshot.md` | 当前进度/阻塞 | 每次联调前后 |
| **注册表** | `docs/agents/02_*` ~ `04_*` | **文件 + 关键函数** | 改代码时同步 |
| **源码** | `robot/firmware/src/*`, `robot/mergetesting/src/*` | 逐行真相 | Git |

当快照和源码不一致时，优先级是：live source / `platformio.ini` > `AGENTS.md` > 最新 dated status > 本目录 registry > 旧快照。

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
| `robot/firmware` + dedicated envs | 小机器人单项功能调试 | 电机/屏幕/相机/麦克风/喇叭先在这里验证 |
| `robot/mergetesting` | **DK-2500/base-station 联调** | WebSocket `/control` `/video` `/audio` |
| `ota_bootstrap` / `ota_bootstrap_wifi` | 无线烧录桥 | 只用于刷新 bootstrap；烧其他 env 必须给该 env 保留 OTA runtime，见 `docs/project_status_2026-06-25.md` |

`docs/project_status_2026-06-22.md` 仍是宽范围硬件/联调 baseline；`docs/project_status_2026-06-25.md` 是 OTA bootstrap 增量，不替代前者。
| `motor_cam_wifi_manual` env | 单机硬件 demo | ESP32 AP + HTTP MJPEG `:81/stream` |

## 刷新注册表（可选）

```powershell
python tools/generate_agent_registry.py
```

会更新 `docs/agents/_generated/` 下的文件清单（不覆盖人工写的状态列）。

## 二级文档（按需，非开工默认）

| 文档 | 用途 |
|------|------|
| `docs/deployment_dk2500.md` | DK-2500 部署（配合最新 project_status） |
| `docs/device_setup.md` | 新机器 OpenFace/VLM |
| `docs/local_api.md` | Local HTTP API |
| `docs/troubleshooting.md` / `docs/model_download.md` | 排障与模型 |
| `docs/openface_au_mapping.md` | OpenFace AU 映射 |
| `docs/frontend_mvp.md` | 前端 MVP |

## Codex 口令速查

| 口令 | 效果 |
|------|------|
| `按 xiao-an-session 开工` + 任务模板 | 读 README/snapshot/registry，输出开工对齐 |
| `按 xiao-an-session 收工` | 验证 + 写回 snapshot/registry，输出收工摘要 |
| `team-lark 对齐进度` | 档位 B：飞书任务表 + 今日简报 |
| `整合 Agent` | 见 01 §9：registry 生成 + dated status |

## 相关文件

- **协作方案（Canonical）：** [01_session_protocol.md](./01_session_protocol.md)
- Codex Skill：`/.agents/skills/xiao-an-session/SKILL.md`
- 飞书协作：`/.agents/skills/team-lark/SKILL.md`
- Cursor（按需）：`/.cursor/rules/agent-session.mdc`
- 人类可读总览：`docs/architecture.md`, `docs/hardware_setup.md`
- Agent 规则：`AGENTS.md`（仓库根）
- 联调对接表：`robot/mergetesting/CAPABILITIES.md`
- 代码边界：`robot/firmware` 验证单项功能，`robot/mergetesting` 负责 base-station 联调；不要把联调入口放回 firmware。
