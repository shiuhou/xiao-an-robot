# 固件源码注册表 — `robot/firmware/src/`

> 每个文件：**角色 | PlatformIO env | 实现状态 | 关键符号 | 最后验证**

## 集成模块（`esp32-s3-devkitc-1` 包含）

| 文件 | 角色 | 状态 | 关键 API / 逻辑 |
|------|------|------|-----------------|
| `main.cpp` | 主入口：WiFi → WS → 命令分发 | ✅ control | `onControlMessage()`, `connectWiFi()`, `setup/loop` |
| `ws_client.cpp/h` | `/control` WS 客户端 | ✅ | `begin()`, `sendHello/Heartbeat/Status`, 指数退避重连 |
| `protocol.h` | 消息 type 常量 | ✅ | `MsgType`, `Expression`, `MotionAction`, `buildMsg()` |
| `motor_ctrl.cpp/h` | DRV8833 差速 | ✅ | `execute()`, `moveForward()`, `turn()`, GPIO1/2/47/38 |
| `display.cpp/h` | 128×160 ST7735 矢量表情 | ✅ | `display_emotion()`, 9 种协议表情 |
| `cam_stream.cpp/h` | OV2640 初始化 + 定时抓帧日志 | 🟡 | `begin()`, `captureLoop()` — **无 WS 推流** |
| `mic_stream.cpp/h` | 麦克风 WS 推流 | ⬜ | 全 TODO |
| `servo_ctrl.cpp/h` | 舵机点头/摆耳 | ⬜ | 全 TODO；main 里 nod 走 servo stub |

### `main.cpp` 命令分发（约 L100–174）

| 收到 type | 处理 | 状态 |
|-----------|------|------|
| `system.welcome` | 日志 + `sendCurrentStatus()` | ✅ |
| `display.expression` | `display_emotion()` | ✅ |
| `motion.execute` | motor/servo 分流 + `motion.completed` | ✅ 电机；⬜ 舵机 |
| `audio.play_tts` / `audio.play_local` | `error.report` AUDIO_UNSUPPORTED | ⬜ |
| `config.update` | TODO NVS | ⬜ |
| `system.shutdown` | `ESP.restart()` | ✅ |

### `ws_client.cpp` 出站消息

| 函数 | type | 间隔/触发 |
|------|------|-----------|
| `sendHello()` | `device.hello` | 连接时 |
| `sendHeartbeat()` | `device.heartbeat` | 10s |
| `sendStatus()` | `device.status` | 事件 |
| `sendMotionCompleted()` | `motion.completed` | 动作后 |
| `sendError()` | `error.report` | 错误 |

---

## 独立测试入口（`*_main.cpp` / `*_test.cpp`）

| 文件 | env | 状态 | 用途 |
|------|-----|------|------|
| `motor_manual_main.cpp` | `motor_manual` | ✅ | 串口 WASD |
| `motor_bench_once_main.cpp` | `motor_bench_once` | ✅ | 一次性方向测试 |
| `motor_wifi_manual_main.cpp` | `motor_wifi_manual` | ✅ | AP 网页控电机 |
| `motor_cam_wifi_manual_main.cpp` | `motor_cam_wifi_manual` | ✅ | AP + MJPEG + 电机 + QR overlay |
| `camtesting_program.cpp` | `camtesting` | ✅ | 相机 AP 流 |
| `keep_face_center_test.cpp` | `keepfacecenter` | 🟡 | 人脸居中 + 电机脉冲 |
| `serial_qr_servo_main.cpp` | `serialqrservo` | 🟡 | 串口 JPEG + PC QR |
| `serial_red_tracker_test.cpp` | `serialredtracker` | 🧪 | 串口红目标 |
| `red_circle_tracker_test.cpp` | `redtracker` | 🧪 | 设备端红圆跟踪 |
| `tft_test.cpp` | `display_test` / `tfttest` | ✅ | 128×160 基础 |
| `face240_roboeyes_test.cpp` | `face240` / `face240_roboeyes` | ✅ | 2.4 寸 RoboEyes 风格 |
| `robot_face_9expr_merged_optimized.cpp` | `face240_9expr_merged` | ✅ | **九表情 merged**（无 shell） |
| `robot_face_9expressions_no_shell.cpp` | — | 🟡 | 旧版，env 需确认 |
| `face240_wire_test.cpp` | `face240_wiretest` | ✅ | 接线/颜色 |
| `face240_espi_test.cpp` | `face240_espi` | 🟡 | TFT_eSPI sprite |
| `face240_raw_design_test.cpp` | — | 🟡 | 另一套 8 表情 |
| `tft_espi_probe.cpp` | `tftprobe_*` (8 env) | ✅ | ST7789 驱动探测 |
| `voice_recognition_test.cpp` | `voice_recognition_test` | ✅ | INMP441 I2S RMS |
| `speaker_amp_test.cpp` | `speaker_amp_test` | ✅ | MAX98357A 音调 |

### 可删除/归档候选

| 文件 | 说明 |
|------|------|
| `gemini-code-1782142240279.cpp` | 临时生成物，不应进主 env |
| `monthly_salary_meow_frames.h` | 与机器人无关的帧数据 |

---

## PlatformIO env 完整列表

见 `robot/firmware/platformio.ini` 中 `[env:*]`。
验证命令见 [05_test_matrix](./05_test_matrix.md)。

---

## 与 mergetesting 的关系

| firmware 源 | mergetesting 对应 |
|-------------|-------------------|
| `motor_ctrl.cpp` | 复制 + 联调脉冲 |
| `display.cpp` | ST7735 分支 |
| `robot_face_9expr_merged_optimized.cpp` | `face240_display.cpp` |
| `voice_recognition_test.cpp` | `mic_stream.cpp` |
| `speaker_amp_test.cpp` | `speaker.cpp` |
| `cam_stream.cpp` | + WS 推流 |
| `ws_client.cpp` | 三通道增强版 |

主固件稳定后，mergetesting 改动应 **回迁** `robot/firmware/src/main.cpp` 与模块。
