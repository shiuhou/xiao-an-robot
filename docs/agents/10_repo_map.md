# 仓库全图 — 目录 / 文档 / 工具索引

> **整合 Agent 维护。** 机器清单见 `_generated/file_inventory.md`（`python tools/generate_agent_registry.py` 刷新）。
> 开工/收工流程见 [01_session_protocol.md](./01_session_protocol.md)。最后整理：**2026-06-27**。

---

## 1. 顶层目录

| 路径 | 用途 | Agent 注册表 |
|------|------|--------------|
| `agent/` | OpenClaw brain、gateway、skills、SQLite schema | [04_base_station_agent_registry](./04_base_station_agent_registry.md) |
| `base_station/` | WS 服务、perception、monitor、Local API | [04_*](./04_base_station_agent_registry.md) |
| `docs/` | 架构、协议、部署、状态、agents 体系 | 本文 + [README](./README.md) |
| `frontend/` | Electron/Vite 早期 UI | [frontend/README.md](../../frontend/README.md) |
| `hardware/` | BOM、接线、机械 | [hardware_setup.md](../hardware_setup.md) |
| `robot/firmware/` | ESP32 本体单项 bring-up | [02_firmware_registry](./02_firmware_registry.md) |
| `robot/mergetesting/` | **DK-2500 联调固件** | [03_mergetesting_registry](./03_mergetesting_registry.md) |
| `scripts/` | 启动/环境脚本（非 Python tools） | 按需读目录 |
| `shared/` | 协议常量、schema、示例 JSON | 改协议必同步 |
| `tests/` | unit + integration + mock_robot | [05_test_matrix](./05_test_matrix.md) |
| `tools/` | 联调/探测 CLI（Python） | [04_* §Tools](./04_base_station_agent_registry.md) |
| `.agents/skills/` | Codex 项目 Skill（**已纳入 Git**） | [01_session_protocol](./01_session_protocol.md) |
| `.cursor/rules/` | Cursor 可选 rule | 用户指定时启用 |

### 根目录文件

| 文件 | 状态 |
|------|------|
| `README.md` | 人类入口 |
| `AGENTS.md` | Agent 仓库规则 + Session Protocol 摘要 |
| `.env.example` | 环境变量模板 |
| `.gitignore` | 忽略 `.pio/`、`runtime/`、`config.local.h`、模型权重等 |

---

## 2. 文档地图（`docs/`）

### 2.1 Agent 体系（优先读）

| 文件 | 作用 |
|------|------|
| [README.md](./README.md) | 入口路由 |
| [01_session_protocol.md](./01_session_protocol.md) | Codex 开工/收工/三档协作 |
| [00_snapshot.md](./00_snapshot.md) | 当前进度 |
| [02~05 registry](./02_firmware_registry.md) | 模块注册表 |
| [06_integration_phases.md](./06_integration_phases.md) | 联调阶段 |
| [07_maintenance.md](./07_maintenance.md) | 何时更新哪些 MD |
| [08_priority_queue.yaml](./08_priority_queue.yaml) | 串行任务队列 |
| [09_hardware_bringup_checklist.md](./09_hardware_bringup_checklist.md) | 上机检查 |
| [10_repo_map.md](./10_repo_map.md) | **本文** |
| `_generated/file_inventory.md` | 自动生成源码/env 清单 |

### 2.2 契约与架构

| 文件 | 作用 |
|------|------|
| [protocol.md](../protocol.md) | WS 消息契约 v0.1 |
| [architecture.md](../architecture.md) | 四模块架构（2026-06-27 已对齐 mergetesting 传画） |

### 2.3 状态快照（dated）

| 文件 | 用途 |
|------|------|
| [project_status_2026-06-22.md](../project_status_2026-06-22.md) | 宽范围 baseline |
| [project_status_2026-06-25.md](../project_status_2026-06-25.md) | OTA bootstrap 增量 |
| [project_status_2026-06-26.md](../project_status_2026-06-26.md) | split env 实机 H + 仓库整理 |

### 2.4 二级文档（按需读，非开工默认）

| 文件 | 何时读 |
|------|--------|
| [deployment_dk2500.md](../deployment_dk2500.md) | DK-2500 部署；**配合** `project_status_2026-06-26` |
| [device_setup.md](../device_setup.md) | 新机器 OpenFace/VLM |
| [hardware_setup.md](../hardware_setup.md) | 硬件接线总览 |
| [local_api.md](../local_api.md) | Local HTTP API |
| [model_download.md](../model_download.md) | 模型下载 |
| [troubleshooting.md](../troubleshooting.md) | 排障 |
| [openface_au_mapping.md](../openface_au_mapping.md) | AU 8 维映射 |
| [frontend_mvp.md](../frontend_mvp.md) | 前端 MVP |
| [xiao_an_power_wiring_diagram.svg](../xiao_an_power_wiring_diagram.svg) | 电源接线图 |

### 2.5 设计 / 计划

| 路径 | 状态 |
|------|------|
| [superpowers/specs/2026-06-25-layered-firmware-architecture-design.md](../superpowers/specs/2026-06-25-layered-firmware-architecture-design.md) | 分层架构 spec |
| [superpowers/plans/2026-06-26-mergetesting-layered-firmware-slice.md](../superpowers/plans/2026-06-26-mergetesting-layered-firmware-slice.md) | **COMPLETE** — Phase 1 已落地 |

### 2.6 归档（勿当真相）

| 路径 | 替代 |
|------|------|
| [docs/archive/](../archive/README.md) | `00_snapshot` + 最新 `project_status_*` |
| 含 `OPENFACE_XIAOAN_PROGRESS_HANDOFF.md` | `openface_au_mapping.md` + `04_*` |
| 含 `hardware_minimum_loop_route_2026-06-17.xml` | `06_integration_phases` + `09_*` |

---

## 3. 固件双线

| 工程 | PlatformIO env 数 | 源码规模（2026-06-27 生成） |
|------|-------------------|---------------------------|
| `robot/firmware` | 见 `_generated` | 顶层 + `peripherals/` |
| `robot/mergetesting` | **21** env | 含 `src/app/`、`src/services/` |

**规则：** 单项硬件先在 firmware 验证 → 同步最小模块到 mergetesting → DK-2500 联调只烧 mergetesting。

Mergetesting 工程内文档：

- `robot/mergetesting/README.md`
- `robot/mergetesting/CAPABILITIES.md`
- `robot/mergetesting/EXTRACTION_MAP.md`
- `robot/mergetesting/m600.md` — M600 mini PC 部署（未进 registry，按需读）

---

## 4. Tools

### 4.1 根目录 `tools/`（Python CLI）

见 [04_base_station_agent_registry §Tools](./04_base_station_agent_registry.md)。

### 4.2 `robot/firmware/tools/`

| 文件 | 用途 |
|------|------|
| `test_face240_raw_dirty_rect.py` | face240 dirty-rect 验证 |
| `test_face240_roboeyes_framebuffer.py` | RoboEyes framebuffer 测试 |
| `face240_preview.html` | 浏览器预览九表情 |
| `wifi_camera_viewer.py` | WiFi 相机查看 |
| `qr_wifi_servo.py` / `qr_visual_servo.py` | QR 视觉伺服 |
| `motor_keyboard.ps1` | 串口键盘控电机 |

---

## 5. 测试

| 目录 | 说明 |
|------|------|
| `tests/unit/` | Python 单元测试 |
| `tests/integration/` | WS / 联调集成测试 |
| `tests/mock_robot/` | mock 机器人 |

跑法：`python -m unittest discover -s tests -p "test_*.py"` — 见 [05_test_matrix](./05_test_matrix.md)。

---

## 6. Git 忽略但可能存在于磁盘

| 路径 | 处理 |
|------|------|
| `robot/*/.pio/` | **可删**；`pio run` 再生 |
| `**/.cache/clangd/` | **可删**；已加入 `.gitignore` |
| `runtime/` | **可删**；WS 运行时日志；若 WS 进程占用需先停服 |
| `robot/*/src/config.local.h` | **保留**；含 WiFi 凭证，勿提交 |
| `base_station/config.yaml` | **保留**；本地配置，勿提交 |
| `base_station/models/*.{bin,onnx,...}` | **保留**；大模型，勿提交 |

---

## 7. 2026-06-27 仓库整理记录

### 已删除（磁盘）

- `robot/firmware/.pio/`
- `robot/mergetesting/.pio/`
- `robot/firmware/.cache/clangd/`

### 已归档

- `OPENFACE_XIAOAN_PROGRESS_HANDOFF.md` → `docs/archive/`
- `docs/hardware_minimum_loop_route_2026-06-17.xml` → `docs/archive/`

### 已对齐

- `.gitignore`：跟踪 `.agents/skills/**`；忽略 `**/.cache/`
- `docs/architecture.md`：mergetesting 已传画/PCM
- `03_mergetesting_registry.md`：补 6 个 control/ping/OTA env
- `02_firmware_registry.md`：补 `peripherals/`
- `04_*`：补全 `tools/` 清单
- `generate_agent_registry.py`：`rglob` 扫描子目录源码
- `_generated/file_inventory.md`：已刷新

### 未自动处理（需人工）

- `runtime/logs/` — WS 服务占用文件时无法删；停服后手动删 `runtime/`
- `docs/deployment_dk2500.md` — 头部仍 pinned 2026-06-22；部署时对照 `project_status_2026-06-26`
- `mergetesting_full_face240(_ota)` 合并实机 H — 见 queue T17

---

## 8. 刷新本图

```powershell
python tools/generate_agent_registry.py
# 人工：更新 registry 状态列、00_snapshot、project_status
```

整合 Agent 收工：更新 §7 日期与「已对齐」列表。
