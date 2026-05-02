# 小安项目 · 进度记录文档
**更新日期：2026-05-03**
**当前里程碑：5月上旬 — 固件实现 & 外设验证阶段**

---

## 项目状态总览

| 模块 | 负责人 | 状态 |
|------|--------|------|
| GitHub 仓库 & 项目结构 | 张子尧 | ✅ 已完成 |
| WebSocket 通信协议定义 | 全员 | ✅ 已完成 |
| ESP32-S3 硬件接线 | 施宇灏 | ✅ 已完成 |
| `ws_client.cpp` 固件实现 | 施宇灏 | ✅ 已完成 |
| 外设独立测试文件 | 施宇灏 | ✅ 已就绪，待烧录验证 |
| 基站 WebSocket 服务端 | 郑斯悦/张子尧 | ✅ 骨架已生成，逻辑填充中 |
| OpenVINO / NPU 模型部署 | 郑斯悦 | 🔄 进行中 |
| OpenClaw Agent + Skills | 张子尧 | 🔄 骨架已建，逻辑待实现 |
| Electron 前端 UI | 张子尧 | ⏳ 待开始 |
| 飞书 / Notion 文档空间 | 全员 | ✅ 已规划，结构已设计 |

---

## 今日完成工作（2026-05-03，施宇灏）

### 1. 硬件接线全部完成
按照 `docs/hardware_setup.md` 完成所有组件接线，包括：
- ESP32-S3 DevKitC-1 主控
- DRV8833 双路电机驱动（N20 减速电机 × 2）
- 限位开关（左/右各一）
- SG90 舵机（耳部 × 2，头部 × 1）
- TFT 表情显示屏（SPI 接口）
- INMP441 MEMS 麦克风（I2S 接口）

### 2. `ws_client.cpp` 完整实现（使用 Claude Code）
实现了完整的 WebSocket 客户端，涵盖以下功能：

| 功能 | 实现方式 |
|------|---------|
| 开机自动连接 `/control` | `WSClient::begin()` → `_ws.begin(host, port, "/control")` |
| 连接后立即发送 `device.hello` | `WStype_CONNECTED` 事件触发 `sendHello()` |
| 每 10 秒发送 `device.heartbeat` | `loop()` 中检查 `millis() - _lastHb >= 10000` |
| Heartbeat 含电量 + WiFi RSSI | `payload["battery"]` + `payload["wifi_rssi"] = WiFi.RSSI()` |
| 指数退避重连 | `_handleReconnect()`：1→2→4→8→16→30s，断线后自动翻倍 |
| JSON 解析 + 回调路由 | `WStype_TEXT` → `deserializeJson` → `_onControl(type, payload)` |

### 3. `main.cpp` 修复 & 消息路由实现
- **Bug 修复**：移除未定义的 `DisplayController display` 全局变量，将 `display.begin()` 改为 `display_init()`
- **`onControlMessage` 完整实现**：覆盖 `protocol.h` 中所有消息类型的路由：
  - `system.welcome` → 串口日志
  - `display.set_emotion` → `display_emotion(expr, intensity)`
  - `motion.execute` → 舵机（tilt_head / wiggle_ears / nod_head）或电机（move / turn / stop）
  - `tts.play` → 串口日志（TODO: I2S DAC 播放）
  - `audio.play_local` → 串口日志（TODO: SPIFFS 播放）
  - `config.update` → 串口日志（TODO: NVS 持久化）
  - `system.shutdown` → `ESP.restart()`

### 4. 四个外设独立测试文件（待烧录）
为避免集成测试时难以定位问题，生成了四个独立 `.ino` 测试脚本：

| 文件 | 测试内容 |
|------|---------|
| `test_1_motor.ino` | N20 电机前进/后退 + 限位开关触发 |
| `test_2_servo.ino` | SG90 耳部舵机摆动验证 |
| `test_3_display.ino` | TFT 屏幕表情渲染测试 |
| `test_4_mic.ino` | INMP441 麦克风音量监测（串口波形） |

---

## 下一步计划（下次 session）

1. **施宇灏**：按顺序烧录并验证四个外设测试脚本（`test_1` → `test_2` → `test_3` → `test_4`）
2. **施宇灏**：验收通过后，实现 `servo_ctrl.cpp`、`motor_ctrl.cpp`、`display.cpp` 各模块真实逻辑
3. **施宇灏**：跑通 ESP32 ↔ 基站握手（`device.hello` → `server.welcome`）端到端验收
4. **郑斯悦**：继续 NPU 情绪识别模型部署
5. **张子尧**：完善基站 WebSocket 服务端音频/视频帧路由

---

## 当前遗留 TODO（固件侧）

- `sendHello()` / `sendHeartbeat()` 中 `battery = 100` 为硬编码，待接 ADC 引脚读取实际电量
- `AUDIO_PLAY_TTS`：需下载 `audio_url` 并推送至 I2S DAC
- `AUDIO_PLAY_LOCAL`：需从 SPIFFS/LittleFS 读取音频文件播放
- `CONFIG_UPDATE`：需将配置字段持久化至 NVS
- WiFi 凭据目前硬编码在 `main.cpp` 宏定义中，需迁移至 NVS

---

*此文档由 Claude Code 根据项目进度自动生成，请团队成员核对后同步至 Notion 知识库。*
