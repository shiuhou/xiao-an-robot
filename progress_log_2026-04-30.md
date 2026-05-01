# 小安项目 · 进度记录文档
**更新日期：2026-04-30**
**当前里程碑：4月下旬 — 网络通信 & 模型部署阶段**

---

## 项目状态总览

| 模块 | 负责人 | 状态 |
|------|--------|------|
| GitHub 仓库 & 项目结构 | 张子尧 | ✅ 已完成 |
| WebSocket 通信协议定义 | 全员 | ✅ 已完成 |
| ESP32-S3 固件骨架 | 施宇灏 | ✅ 骨架已生成，`ws_client.cpp` 实现中 |
| 基站 WebSocket 服务端 | 郑斯悦/张子尧 | ✅ 骨架已生成，逻辑填充中 |
| OpenVINO / NPU 模型部署 | 郑斯悦 | 🔄 进行中 |
| OpenClaw Agent + Skills | 张子尧 | 🔄 骨架已建，逻辑待实现 |
| Electron 前端 UI | 张子尧 | ⏳ 待开始 |
| 飞书 / Notion 文档空间 | 全员 | ✅ 已规划，结构已设计 |

---

## 已完成的工作（截至今日）

### 1. 机器人外壳 CAD 设计（今日新增）
使用 **Python `build123d` 库** 通过代码驱动方式生成机器人底盘 STEP/STL 文件。

**工具选型讨论结果：**
- 对比了 SolidWorks / Onshape / Tripo 3D / Python build123d 四种方案
- 最终采用 **Python build123d → 导出 STEP → 可选导入 Onshape 精调** 的混合方案

**已设计的部件：底盘（robot_chassis）**
| 参数 | 值 |
|------|----|
| 尺寸 | 120mm × 100mm × 30mm |
| 圆角 | R12mm（垂直边）/ R4mm（顶面） |
| 电机槽 | N20 电机槽 × 2，两侧对称，26mm深 |
| 车轮弧槽 | 半径 23mm（43mm轮 + 3mm间隙），两侧贯通 |
| 机身连接柱 | 顶部中央圆柱 Φ30mm × H6mm |
| 走线孔 | Φ12mm 中心通孔（贯穿底盘+连接柱） |
| 输出文件 | `robot_chassis.step` + `robot_chassis.stl` |

**打印参数建议：**
- 材料：PLA，层高 0.2mm，填充 20%，外壳厚度 2mm

**下一步 CAD 任务：**
- [ ] 上半身外壳（蛋形/球形，含 TFT 屏开口、摄像头孔、耳朵舵机位）
- [ ] Dock 充电底座
- [ ] 轮子（43mm，3mm轴径）

---

### 2. 仓库初始化与项目结构
- 完成 GitHub 仓库 `xiao-an-robot` 搭建，三名成员均已加入
- 使用 GitHub Copilot Agent 生成完整目录骨架，包含所有模块的 stub 文件
- 确认 `.gitignore` 正确排除模型文件、SQLite 数据库、用户隐私数据（`USER.md`）

**仓库结构：**
```
xiao-an-robot/
├── robot/firmware/src/       # ESP32-S3 C/C++ 固件
├── base_station/             # Intel DK-2500 边缘推理 (Python)
│   ├── perception/           # 情绪识别、ASR、TTS、VAD
│   ├── monitor/              # 屏幕监控、SQLite 写入
│   └── ws_server/            # WebSocket 服务端
├── agent/                    # OpenClaw Agent + 8个Skill
│   ├── core/                 # brain, memory, gateway, llm_client
│   └── skills/               # 8个功能插件
├── frontend/                 # Electron 基站 UI
└── docs/                     # 协议文档、硬件指南、周志
```

### 2. WebSocket 通信协议（`docs/protocol.md`）
定义了机器人 ↔ 基站之间的完整 JSON 消息协议，涵盖：
- **Robot → Base Station**：`device.hello`、`device.heartbeat`、`motion.completed`、`error.report`
- **Base Station → Robot**：`server.welcome`、`display.set_emotion`、`motion.drive`、`motion.servo`、`tts.play`、`display.text`
- 三条并行通道：`/control`（JSON 指令）、`/audio`（PCM 音频帧）、`/video`（JPEG 视频帧）

### 3. ESP32-S3 固件骨架
以下模块均已生成 stub，含接口定义和 TODO 注释：
- `motor_ctrl` — 直流电机 + 限位开关控制
- `servo_ctrl` — 耳朵/头部舵机
- `display` — TFT 表情屏渲染
- `mic_stream` — INMP441 麦克风 I2S 采集
- `cam_stream` — OV2640 视频推流
- `ws_client` — WebSocket 收发（**正在实现完整逻辑**）
- `protocol.h` — 共享 JSON 协议常量定义

### 4. `ws_client.cpp` 实现（今日工作重点）
正在使用 Claude Code 实现完整的 WebSocket 客户端，功能要求：
- 开机自动连接基站（`/control` 路径）
- 连接成功后立即发送 `device.hello`
- 每 10 秒发送一次 `device.heartbeat`（含电量、WiFi 信号强度）
- 指数退避重连（1s → 2s → 4s → 8s → 16s → 30s 上限）
- 收到消息后解析 JSON `type` 字段，回调给各子模块（电机/舵机/TFT/TTS）

### 5. 基站 WebSocket 服务端骨架（`base_station/ws_server/server.py`）
已生成可运行的基础服务端，当前实现：
- 路由分发：`/control`、`/audio`、`/video` 三个独立处理器
- 处理 `device.hello` 握手，生成 `session_id` 并返回 `server.welcome`
- 处理 `device.heartbeat`（更新 session 状态）
- 处理 `motion.completed` 回调
- 维护 sessions 字典（device_id → websocket + 状态）

### 6. 团队协作工具规划
- **分支策略**：`main`（保护）/ `develop`（主开发线）/ `feature/*` / `bugfix/*`
- **Commit 规范**：`feat(module):` / `fix(module):` / `docs:` / `test:`
- **Notion 知识库**：已设计结构（学习笔记、踩坑日志、决策记录、进度看板）
- **飞书**：任务看板多维表格已规划字段

---

## 当前阶段目标（4月下旬 — 网络与模型部署）

- [ ] `ws_client.cpp` 完整实现并在 ESP32-S3 上验证通信
- [ ] 基站端跑通本地 VAD（Silero-VAD）+ ASR（Sherpa-ONNX）链路
- [ ] Intel NPU 上部署 `emotions-recognition-retail-0003` 情绪识别模型
- [ ] 验收：ESP32 发送消息 → 基站接收 → 返回 JSON 控制指令 → ESP32 串口打印

---

## 技术栈备忘

| 层级 | 工具/库 | 用途 |
|------|---------|------|
| 固件 | PlatformIO + ArduinoWebsockets + ArduinoJson + TFT_eSPI | ESP32-S3 开发 |
| 视觉推理 | OpenVINO >= 2024.0 + `emotions-recognition-retail-0003` | NPU 情绪识别 |
| 语音 | Sherpa-ONNX + Silero-VAD + edge-tts | ASR / VAD / TTS |
| Agent | OpenClaw + 云端 LLM（Claude / GPT） | 决策中枢 |
| 通信 | WebSocket + RTSP + WiFi | 机器人 ↔ 基站 |
| 数据 | SQLite（emotions.db）+ USER.md | 情绪历史 + 用户画像 |
| 前端 | Electron 28+ + HTML/JS/CSS | 基站大屏 UI |
| 系统 | Ubuntu 22.04 LTS | Intel DK-2500 基站 |

---

## 踩坑 & 注意事项

- **模型不入库**：所有 `.bin` / `.xml` / `.onnx` / `.pth` 文件通过 `models/download_models.sh` 单独下载，`.gitignore` 已配置
- **隐私数据不入库**：`agent/data/USER.md`、`agent/data/*.db` 已排除
- **不要一次塞所有模块进 main.cpp**：每个外设独立测试脚本，出问题方便定位
- **云端 LLM 先用 requests 直接调通，再接 OpenClaw**：避免过早引入框架复杂性

---

## 下一步计划

1. **施宇灏**：完成 `ws_client.cpp` 并在 ESP32 上跑通与基站的握手
2. **郑斯悦**：在 DK-2500 的 NPU 上完成情绪识别模型部署，输出情绪标签
3. **张子尧**：完善基站 WebSocket 服务端的音频/视频帧路由逻辑

---

*此文档由 Claude 根据项目对话记录自动生成，请团队成员核对后更新至 Notion 知识库或 `docs/weekly_log.md`。*
